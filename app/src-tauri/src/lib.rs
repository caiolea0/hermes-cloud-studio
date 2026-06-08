use serde::Serialize;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;
const DETACHED_PROCESS: u32 = 0x00000008;
// Combinacao defensiva: CREATE_NO_WINDOW sozinho nao basta pra ssh.exe nativo
// (OpenSSH ignora e mostra console flash). DETACHED_PROCESS desconecta do console parent.
const HIDDEN_PROC_FLAGS: u32 = CREATE_NO_WINDOW | DETACHED_PROCESS;

use tauri::{
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
    AppHandle, Manager, State,
};

// ===========================================================================
// State
// ===========================================================================

struct RestartTracker {
    attempts: u32,
    timestamps: Vec<Instant>,
    last_healthy: Option<Instant>,
    in_cooldown: bool,
    cooldown_until: Option<Instant>,
}

impl RestartTracker {
    fn new() -> Self {
        Self {
            attempts: 0,
            timestamps: Vec::new(),
            last_healthy: None,
            in_cooldown: false,
            cooldown_until: None,
        }
    }

    /// Returns true if restart is allowed
    fn can_restart(&mut self) -> bool {
        let now = Instant::now();

        // Check cooldown
        if self.in_cooldown {
            if let Some(until) = self.cooldown_until {
                if now >= until {
                    self.in_cooldown = false;
                    self.cooldown_until = None;
                    self.attempts = 0;
                    self.timestamps.clear();
                } else {
                    return false;
                }
            }
        }

        // Purge timestamps older than 60s
        self.timestamps.retain(|t| now.duration_since(*t) < Duration::from_secs(60));

        if self.timestamps.len() >= 3 {
            // Too many restarts in 60s window — enter cooldown
            self.in_cooldown = true;
            self.cooldown_until = Some(now + Duration::from_secs(60));
            return false;
        }

        self.timestamps.push(now);
        self.attempts += 1;
        true
    }

    /// Call when service is confirmed healthy
    fn mark_healthy(&mut self) {
        let now = Instant::now();
        if let Some(last) = self.last_healthy {
            // If healthy for 30s+, reset tracker
            if now.duration_since(last) >= Duration::from_secs(30) {
                self.attempts = 0;
                self.timestamps.clear();
            }
        }
        self.last_healthy = Some(now);
    }

    fn status_text(&self) -> &'static str {
        if self.in_cooldown {
            "cooldown"
        } else if self.attempts > 0 {
            "recovering"
        } else {
            "ok"
        }
    }
}

struct AppServices {
    server_proc: Mutex<Option<Child>>,
    proxy_proc: Mutex<Option<Child>>,
    tunnel_proc: Mutex<Option<Child>>,
    project_dir: Mutex<PathBuf>,
    server_tracker: Mutex<RestartTracker>,
    proxy_tracker: Mutex<RestartTracker>,
    tunnel_tracker: Mutex<RestartTracker>,
    shutdown: Mutex<bool>,
}

#[derive(Serialize, Clone)]
struct ServiceStatus {
    server: bool,
    proxy: bool,
    tunnel: bool,
    server_status: String,
    proxy_status: String,
    tunnel_status: String,
}

// ===========================================================================
// Helpers
// ===========================================================================

fn is_port_open(port: u16) -> bool {
    TcpStream::connect(format!("127.0.0.1:{}", port))
        .map(|_| true)
        .unwrap_or(false)
}

fn is_process_alive(proc: &Mutex<Option<Child>>) -> bool {
    let mut guard = proc.lock().unwrap();
    match guard.as_mut() {
        Some(c) => matches!(c.try_wait(), Ok(None)),
        None => false,
    }
}

fn project_dir() -> PathBuf {
    let exe = std::env::current_exe().unwrap_or_default();
    let mut dir = exe.parent().unwrap_or(std::path::Path::new(".")).to_path_buf();

    // Walk up until we find server.py
    for _ in 0..8 {
        if dir.join("server.py").exists() {
            return dir;
        }
        if let Some(parent) = dir.parent() {
            dir = parent.to_path_buf();
        } else {
            break;
        }
    }

    // Fallback: hardcoded dev path
    PathBuf::from(r"D:\dev-projects\main\hermes-cloud-studio")
}

/// True se tunnel_supervisor.py atualizou state.json nos ultimos 90s.
/// Usado pra delegar controle de ssh tunnel ao supervisor (evita conflito 2 ssh em :55081).
fn supervisor_is_active() -> bool {
    use std::time::SystemTime;
    let exe = match std::env::current_exe() {
        Ok(e) => e,
        Err(_) => return false,
    };
    let mut p = exe.clone();
    for _ in 0..6 {
        if let Some(parent) = p.parent() {
            let candidate = parent.join("logs").join("tunnel_supervisor_state.json");
            if candidate.exists() {
                if let Ok(meta) = std::fs::metadata(&candidate) {
                    if let Ok(modified) = meta.modified() {
                        if let Ok(elapsed) = SystemTime::now().duration_since(modified) {
                            return elapsed.as_secs() < 90;
                        }
                    }
                }
            }
            p = parent.to_path_buf();
        } else {
            break;
        }
    }
    false
}

#[cfg(windows)]
fn spawn_hidden(cmd: &str, args: &[&str], cwd: Option<&PathBuf>) -> Result<Child, String> {
    let mut command = Command::new(cmd);
    command.args(args);
    // Flags combinadas: CREATE_NO_WINDOW (hide GUI) + DETACHED_PROCESS (cut from parent console).
    // ssh.exe OpenSSH nativo ignora CREATE_NO_WINDOW sozinho — DETACHED_PROCESS forca hide.
    command.creation_flags(HIDDEN_PROC_FLAGS);
    command.stdout(std::process::Stdio::null());
    command.stderr(std::process::Stdio::null());
    command.stdin(std::process::Stdio::null());
    if let Some(d) = cwd {
        command.current_dir(d);
    }
    command.spawn().map_err(|e| e.to_string())
}

#[cfg(not(windows))]
fn spawn_hidden(cmd: &str, args: &[&str], cwd: Option<&PathBuf>) -> Result<Child, String> {
    let mut command = Command::new(cmd);
    command.args(args);
    command.stdout(std::process::Stdio::null());
    command.stderr(std::process::Stdio::null());
    if let Some(d) = cwd {
        command.current_dir(d);
    }
    command.spawn().map_err(|e| e.to_string())
}

// ===========================================================================
// Service Launchers
// ===========================================================================

fn launch_server(services: &AppServices) -> Result<(), String> {
    if is_port_open(55000) {
        return Ok(());
    }
    let dir = services.project_dir.lock().unwrap().clone();
    let server_py = dir.join("server.py");
    if !server_py.exists() {
        return Err(format!("server.py not found in {:?}", dir));
    }

    let child = spawn_hidden(
        "python",
        &[server_py.to_str().unwrap()],
        Some(&dir),
    )?;
    *services.server_proc.lock().unwrap() = Some(child);
    Ok(())
}

fn launch_proxy(services: &AppServices) -> Result<(), String> {
    if is_port_open(55081) {
        return Ok(());
    }
    let dir = services.project_dir.lock().unwrap().clone();
    let proxy_py = dir.join("socks5_proxy.py");
    if !proxy_py.exists() {
        return Ok(()); // proxy is optional
    }
    let child = spawn_hidden(
        "python",
        &[proxy_py.to_str().unwrap(), "55081"],
        Some(&dir),
    )?;
    *services.proxy_proc.lock().unwrap() = Some(child);
    Ok(())
}

fn launch_tunnel(services: &AppServices) -> Result<(), String> {
    if is_process_alive(&services.tunnel_proc) {
        return Ok(());
    }
    // Delega pro tunnel_supervisor.py se ele esta ativo (state.json recente).
    // Evita conflito de 2 ssh tunnels concorrentes no mesmo :55081 da VM,
    // que causava console flash periodico do ssh.exe respawnando.
    if supervisor_is_active() {
        return Ok(());
    }
    let child = spawn_hidden(
        "ssh",
        &[
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-R", "127.0.0.1:55081:127.0.0.1:55081",
            "-R", "127.0.0.1:11434:127.0.0.1:11434",  // Ollama GPU → VM
            "-N", "hermes-gcp@136.115.74.69",
        ],
        None,
    )?;
    *services.tunnel_proc.lock().unwrap() = Some(child);
    Ok(())
}

// ===========================================================================
// Health Check Loop
// ===========================================================================

fn spawn_health_loop(app_handle: AppHandle) {
    std::thread::spawn(move || {
        // Wait initial 5s for services to settle
        std::thread::sleep(Duration::from_secs(5));

        loop {
            std::thread::sleep(Duration::from_secs(10));

            let services = app_handle.state::<AppServices>();

            // Check if app is shutting down
            if *services.shutdown.lock().unwrap() {
                break;
            }

            // --- Server health ---
            if is_port_open(55000) {
                services.server_tracker.lock().unwrap().mark_healthy();
            } else {
                let mut tracker = services.server_tracker.lock().unwrap();
                if tracker.can_restart() {
                    drop(tracker); // release lock before launching
                    let _ = launch_server(services.inner());
                }
            }

            // --- Proxy health ---
            if is_port_open(55081) {
                services.proxy_tracker.lock().unwrap().mark_healthy();
            } else {
                let mut tracker = services.proxy_tracker.lock().unwrap();
                if tracker.can_restart() {
                    drop(tracker);
                    let _ = launch_proxy(services.inner());
                }
            }

            // --- Tunnel health ---
            if is_process_alive(&services.tunnel_proc) {
                services.tunnel_tracker.lock().unwrap().mark_healthy();
            } else {
                let mut tracker = services.tunnel_tracker.lock().unwrap();
                if tracker.can_restart() {
                    drop(tracker);
                    let _ = launch_tunnel(services.inner());
                }
            }

            // Update tray tooltip with status
            let s_status = services.server_tracker.lock().unwrap().status_text();
            let p_status = services.proxy_tracker.lock().unwrap().status_text();
            let t_status = services.tunnel_tracker.lock().unwrap().status_text();

            let tooltip = format!(
                "Hermes | Server: {} | Proxy: {} | Tunnel: {}",
                s_status, p_status, t_status
            );
            if let Some(tray) = app_handle.tray_by_id("main-tray") {
                let _ = tray.set_tooltip(Some(&tooltip));
            }
        }
    });
}

/// Wait for server port with timeout, then show window
fn wait_and_show_window(app_handle: AppHandle) {
    std::thread::spawn(move || {
        let max_wait = Duration::from_secs(15);
        let start = Instant::now();
        let interval = Duration::from_millis(500);

        while start.elapsed() < max_wait {
            if is_port_open(55000) {
                // Small extra delay for server to be fully ready
                std::thread::sleep(Duration::from_millis(500));
                if let Some(w) = app_handle.get_webview_window("main") {
                    let _ = w.show();
                    let _ = w.set_focus();
                }
                return;
            }
            std::thread::sleep(interval);
        }

        // Timeout: show window anyway (will show error/loading in browser)
        if let Some(w) = app_handle.get_webview_window("main") {
            let _ = w.show();
            let _ = w.set_focus();
        }
    });
}

// ===========================================================================
// Tauri Commands
// ===========================================================================

#[tauri::command]
fn get_status(services: State<AppServices>) -> ServiceStatus {
    ServiceStatus {
        server: is_port_open(55000),
        proxy: is_port_open(55081),
        tunnel: is_process_alive(&services.tunnel_proc),
        server_status: services.server_tracker.lock().unwrap().status_text().to_string(),
        proxy_status: services.proxy_tracker.lock().unwrap().status_text().to_string(),
        tunnel_status: services.tunnel_tracker.lock().unwrap().status_text().to_string(),
    }
}

#[tauri::command]
fn start_server(services: State<AppServices>) -> Result<String, String> {
    launch_server(&services)?;
    Ok("started".into())
}

#[tauri::command]
fn start_proxy(services: State<AppServices>) -> Result<String, String> {
    launch_proxy(&services)?;
    Ok("started".into())
}

#[tauri::command]
fn start_tunnel(services: State<AppServices>) -> Result<String, String> {
    launch_tunnel(&services)?;
    Ok("started".into())
}

#[tauri::command]
fn stop_tunnel(services: State<AppServices>) -> String {
    do_stop_proc(&services.tunnel_proc);
    "stopped".into()
}

#[tauri::command]
fn toggle_tunnel(services: State<AppServices>) -> Result<ServiceStatus, String> {
    if is_process_alive(&services.tunnel_proc) {
        do_stop_proc(&services.tunnel_proc);
    } else {
        // Ensure proxy is running first
        let _ = launch_proxy(&services);
        std::thread::sleep(Duration::from_secs(1));
        launch_tunnel(&services)?;
        std::thread::sleep(Duration::from_secs(2));
    }
    Ok(get_status(services))
}

/// Le auth tokens do .env e retorna pro frontend.
/// IPC command que substitui o modal "Cole token de acesso" — usuario nao precisa
/// mais digitar token manualmente quando dashboard abrir via Tauri.
#[derive(Clone, serde::Serialize)]
struct AuthTokens {
    auth_token: String,
    internal_token: String,
    dashboard_port: u16,
}

#[tauri::command]
fn get_auth_tokens() -> Result<AuthTokens, String> {
    use std::env;
    use std::fs;
    use std::path::PathBuf;

    // Caminho do .env relativo ao executavel: app/src-tauri/target/release/hermes.exe
    // .env esta em D:\dev-projects\main\hermes-cloud-studio\.env -> 3 levels up
    let exe = env::current_exe().map_err(|e| format!("current_exe: {}", e))?;
    let mut env_path: PathBuf = exe.clone();
    // Tentar candidatos
    let candidates: Vec<PathBuf> = vec![
        env_path.parent().and_then(|p| p.parent()).and_then(|p| p.parent()).and_then(|p| p.parent()).map(|p| p.join(".env")).unwrap_or_default(),
        env_path.parent().and_then(|p| p.parent()).and_then(|p| p.parent()).map(|p| p.join(".env")).unwrap_or_default(),
        env_path.parent().and_then(|p| p.parent()).map(|p| p.join(".env")).unwrap_or_default(),
    ];
    env_path = candidates.into_iter().find(|p| p.exists()).ok_or_else(|| ".env nao encontrado relativo ao exe".to_string())?;

    let content = fs::read_to_string(&env_path).map_err(|e| format!("read .env: {}", e))?;
    let mut auth_token = String::new();
    let mut internal_token = String::new();
    let mut dashboard_port: u16 = 55000;

    for line in content.lines() {
        let line = line.trim();
        if line.starts_with('#') || line.is_empty() { continue; }
        if let Some((k, v)) = line.split_once('=') {
            let k = k.trim();
            let v = v.trim().trim_matches(|c| c == '"' || c == '\'').to_string();
            match k {
                "HERMES_AUTH_TOKEN" => auth_token = v,
                "HERMES_INTERNAL_TOKEN" => internal_token = v,
                "DASHBOARD_PORT" => dashboard_port = v.parse().unwrap_or(55000),
                _ => {}
            }
        }
    }

    if auth_token.is_empty() {
        return Err("HERMES_AUTH_TOKEN ausente no .env".to_string());
    }
    Ok(AuthTokens { auth_token, internal_token, dashboard_port })
}

fn do_stop_proc(proc: &Mutex<Option<Child>>) {
    let mut guard = proc.lock().unwrap();
    if let Some(ref mut child) = *guard {
        let _ = child.kill();
        let _ = child.wait();
    }
    *guard = None;
}

// ===========================================================================
// Tray
// ===========================================================================

fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let show = MenuItemBuilder::with_id("show", "Abrir Dashboard").build(app)?;
    let toggle = MenuItemBuilder::with_id("toggle_tunnel", "Ligar/Desligar Tunnel").build(app)?;
    let restart_all = MenuItemBuilder::with_id("restart_all", "Reiniciar Servicos").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "Sair").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&show)
        .separator()
        .item(&toggle)
        .item(&restart_all)
        .separator()
        .item(&quit)
        .build()?;

    let icon_bytes: &[u8] = include_bytes!("../icons/32x32.png");
    let icon = Image::from_bytes(icon_bytes)?;

    let _tray = TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .tooltip("Hermes Command Center")
        .menu(&menu)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "show" => {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.show();
                    let _ = w.set_focus();
                }
            }
            "toggle_tunnel" => {
                let services = app.state::<AppServices>();
                if is_process_alive(&services.tunnel_proc) {
                    do_stop_proc(&services.tunnel_proc);
                } else {
                    let _ = launch_proxy(services.inner());
                    std::thread::sleep(Duration::from_secs(1));
                    let _ = launch_tunnel(services.inner());
                }
            }
            "restart_all" => {
                let services = app.state::<AppServices>();
                // Kill existing
                do_stop_proc(&services.server_proc);
                do_stop_proc(&services.proxy_proc);
                do_stop_proc(&services.tunnel_proc);
                // Reset trackers
                *services.server_tracker.lock().unwrap() = RestartTracker::new();
                *services.proxy_tracker.lock().unwrap() = RestartTracker::new();
                *services.tunnel_tracker.lock().unwrap() = RestartTracker::new();
                // Relaunch
                std::thread::sleep(Duration::from_secs(1));
                let _ = launch_server(services.inner());
                let _ = launch_proxy(services.inner());
                let _ = launch_tunnel(services.inner());
            }
            "quit" => {
                let services = app.state::<AppServices>();
                *services.shutdown.lock().unwrap() = true;
                do_stop_proc(&services.server_proc);
                do_stop_proc(&services.proxy_proc);
                do_stop_proc(&services.tunnel_proc);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

// ===========================================================================
// Entry
// ===========================================================================

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let dir = project_dir();

    let services = AppServices {
        server_proc: Mutex::new(None),
        proxy_proc: Mutex::new(None),
        tunnel_proc: Mutex::new(None),
        project_dir: Mutex::new(dir),
        server_tracker: Mutex::new(RestartTracker::new()),
        proxy_tracker: Mutex::new(RestartTracker::new()),
        tunnel_tracker: Mutex::new(RestartTracker::new()),
        shutdown: Mutex::new(false),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(services)
        .invoke_handler(tauri::generate_handler![
            get_status,
            start_server,
            start_proxy,
            start_tunnel,
            stop_tunnel,
            toggle_tunnel,
            get_auth_tokens,
        ])
        .setup(|app| {
            let svc = app.state::<AppServices>();

            // Launch all services (invisible, no console)
            let _ = launch_server(svc.inner());
            let _ = launch_proxy(svc.inner());
            let _ = launch_tunnel(svc.inner());

            // Setup tray icon
            setup_tray(app)?;

            // Spawn health monitor thread
            spawn_health_loop(app.handle().clone());

            // Wait for server, then show window
            wait_and_show_window(app.handle().clone());

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Hermes");
}
