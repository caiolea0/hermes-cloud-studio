use serde::Serialize;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;
use tauri::{
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
    Manager, State,
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
struct AppServices {
    server_proc: Mutex<Option<Child>>,
    proxy_proc: Mutex<Option<Child>>,
    tunnel_proc: Mutex<Option<Child>>,
    project_dir: Mutex<PathBuf>,
}

#[derive(Serialize, Clone)]
struct ServiceStatus {
    server: bool,
    proxy: bool,
    tunnel: bool,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
fn is_port_open(port: u16) -> bool {
    TcpStream::connect(format!("127.0.0.1:{}", port)).is_ok()
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
    // In dev: src-tauri/target/debug/hermes.exe -> go up to app, then up to hermes-vm
    // In prod: installed next to hermes-vm or configured
    let mut dir = exe.parent().unwrap_or(std::path::Path::new(".")).to_path_buf();

    // Walk up until we find server.py
    for _ in 0..6 {
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

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------
#[tauri::command]
fn get_status(services: State<AppServices>) -> ServiceStatus {
    let server = is_port_open(8500);
    let proxy = is_port_open(1081);
    let tunnel_alive = is_process_alive(&services.tunnel_proc);
    ServiceStatus {
        server,
        proxy,
        tunnel: tunnel_alive && proxy,
    }
}

#[tauri::command]
fn start_server(services: State<AppServices>) -> Result<String, String> {
    if is_port_open(8500) {
        return Ok("already running".into());
    }
    let dir = services.project_dir.lock().unwrap().clone();
    let server_py = dir.join("server.py");
    if !server_py.exists() {
        return Err(format!("server.py not found in {:?}", dir));
    }
    let child = Command::new("python")
        .arg(server_py.to_str().unwrap())
        .current_dir(&dir)
        .stdout(std::process::Stdio::null())
        .stderr(std::fs::File::create(dir.join("server_err.log")).map_err(|e| e.to_string())?)
        .spawn()
        .map_err(|e| e.to_string())?;

    *services.server_proc.lock().unwrap() = Some(child);
    Ok("started".into())
}

#[tauri::command]
fn start_proxy(services: State<AppServices>) -> Result<String, String> {
    if is_port_open(1081) {
        return Ok("already running".into());
    }
    let dir = services.project_dir.lock().unwrap().clone();
    let proxy_py = dir.join("socks5_proxy.py");
    if !proxy_py.exists() {
        return Err("socks5_proxy.py not found".into());
    }
    let child = Command::new("python")
        .args([proxy_py.to_str().unwrap(), "1081"])
        .creation_flags(CREATE_NO_WINDOW) // CREATE_NO_WINDOW
        .spawn()
        .map_err(|e| e.to_string())?;

    *services.proxy_proc.lock().unwrap() = Some(child);
    Ok("started".into())
}

#[tauri::command]
fn start_tunnel(services: State<AppServices>) -> Result<String, String> {
    if is_process_alive(&services.tunnel_proc) {
        return Ok("already running".into());
    }
    let child = Command::new("ssh")
        .args([
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-R", "127.0.0.1:1081:127.0.0.1:1081",
            "-N", "hermes-gcp@136.115.74.69",
        ])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| e.to_string())?;

    *services.tunnel_proc.lock().unwrap() = Some(child);
    Ok("started".into())
}

fn do_stop_tunnel(services: &AppServices) {
    let mut proc = services.tunnel_proc.lock().unwrap();
    if let Some(ref mut child) = *proc {
        let _ = child.kill();
        let _ = child.wait();
    }
    *proc = None;
}

#[tauri::command]
fn stop_tunnel(services: State<AppServices>) -> String {
    do_stop_tunnel(&services);
    "stopped".into()
}

#[tauri::command]
fn toggle_tunnel(services: State<AppServices>) -> Result<ServiceStatus, String> {
    let alive = is_process_alive(&services.tunnel_proc);
    if alive {
        do_stop_tunnel(&services);
    } else {
        // start proxy if not running
        if !is_port_open(1081) {
            let dir = services.project_dir.lock().unwrap().clone();
            let proxy_py = dir.join("socks5_proxy.py");
            if proxy_py.exists() {
                if let Ok(child) = Command::new("python")
                    .args([proxy_py.to_str().unwrap(), "1081"])
                    .creation_flags(CREATE_NO_WINDOW)
                    .spawn()
                {
                    *services.proxy_proc.lock().unwrap() = Some(child);
                }
            }
            std::thread::sleep(std::time::Duration::from_secs(1));
        }
        // start tunnel
        if let Ok(child) = Command::new("ssh")
            .args([
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-R", "127.0.0.1:1081:127.0.0.1:1081",
                "-N", "hermes-gcp@136.115.74.69",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
        {
            *services.tunnel_proc.lock().unwrap() = Some(child);
        }
        std::thread::sleep(std::time::Duration::from_secs(2));
    }
    Ok(ServiceStatus {
        server: is_port_open(8500),
        proxy: is_port_open(1081),
        tunnel: is_process_alive(&services.tunnel_proc),
    })
}

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------
fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let show = MenuItemBuilder::with_id("show", "Abrir Dashboard").build(app)?;
    let toggle = MenuItemBuilder::with_id("toggle_tunnel", "Ligar/Desligar Tunnel").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "Sair").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&show)
        .separator()
        .item(&toggle)
        .separator()
        .item(&quit)
        .build()?;

    let icon_bytes: &[u8] = include_bytes!("../icons/32x32.png");
    let icon = Image::from_bytes(icon_bytes)?;

    let _tray = TrayIconBuilder::new()
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
                let alive = is_process_alive(&services.tunnel_proc);
                if alive {
                    do_stop_tunnel(&services);
                } else {
                    let _ = Command::new("ssh")
                        .args([
                            "-o", "StrictHostKeyChecking=no",
                            "-o", "ServerAliveInterval=30",
                            "-R", "127.0.0.1:1081:127.0.0.1:1081",
                            "-N", "hermes-gcp@136.115.74.69",
                        ])
                        .creation_flags(CREATE_NO_WINDOW)
                        .spawn()
                        .map(|child| {
                            *services.tunnel_proc.lock().unwrap() = Some(child);
                        });
                }
            }
            "quit" => {
                let services = app.state::<AppServices>();
                do_stop_tunnel(&services);
                if let Some(ref mut c) = *services.server_proc.lock().unwrap() {
                    let _ = c.kill();
                }
                if let Some(ref mut c) = *services.proxy_proc.lock().unwrap() {
                    let _ = c.kill();
                }
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let dir = project_dir();

    let services = AppServices {
        server_proc: Mutex::new(None),
        proxy_proc: Mutex::new(None),
        tunnel_proc: Mutex::new(None),
        project_dir: Mutex::new(dir),
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
        ])
        .setup(|app| {
            let svc = app.state::<AppServices>();

            // Start server
            if !is_port_open(8500) {
                let dir = svc.project_dir.lock().unwrap().clone();
                let server_py = dir.join("server.py");
                if server_py.exists() {
                    if let Ok(child) = Command::new("python")
                        .arg(server_py.to_str().unwrap())
                        .current_dir(&dir)
                        .stdout(std::process::Stdio::null())
                        .stderr(std::fs::File::create(dir.join("server_err.log")).unwrap_or_else(|_| {
                            std::fs::File::create(std::env::temp_dir().join("hermes_err.log")).unwrap()
                        }))
                        .spawn()
                    {
                        *svc.server_proc.lock().unwrap() = Some(child);
                    }
                }
                std::thread::sleep(std::time::Duration::from_secs(2));
            }

            // Start proxy
            if !is_port_open(1081) {
                let dir = svc.project_dir.lock().unwrap().clone();
                let proxy_py = dir.join("socks5_proxy.py");
                if proxy_py.exists() {
                    if let Ok(child) = Command::new("python")
                        .args([proxy_py.to_str().unwrap(), "1081"])
                        .creation_flags(CREATE_NO_WINDOW)
                        .spawn()
                    {
                        *svc.proxy_proc.lock().unwrap() = Some(child);
                    }
                }
                std::thread::sleep(std::time::Duration::from_secs(1));
            }

            // Start tunnel
            if let Ok(child) = Command::new("ssh")
                .args([
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "ServerAliveInterval=30",
                    "-o", "ServerAliveCountMax=3",
                    "-R", "127.0.0.1:1081:127.0.0.1:1081",
                    "-N", "hermes-gcp@136.115.74.69",
                ])
                .creation_flags(CREATE_NO_WINDOW)
                .spawn()
            {
                *svc.tunnel_proc.lock().unwrap() = Some(child);
            }

            setup_tray(app)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Hermes");
}
