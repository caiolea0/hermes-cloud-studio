-- Hermes 2.0 basemap — tilemaker v3 process script
-- Layers: transportation, waterway, water, landuse, building
-- No Natural Earth dependency (zoom 8-14 city level)
-- API v3: global Find(), Layer(), Attribute() — no way object arg

node_keys = {}   -- no node processing needed

function way_function()
  local hw = Find("highway")

  -- ── Transportation ────────────────────────────────────────────────────
  if hw ~= "" then
    local class = "minor"
    if     hw == "motorway"   or hw == "motorway_link"  then class = "motorway"
    elseif hw == "trunk"      or hw == "trunk_link"     then class = "trunk"
    elseif hw == "primary"    or hw == "primary_link"   then class = "primary"
    elseif hw == "secondary"  or hw == "secondary_link" then class = "secondary"
    elseif hw == "tertiary"   or hw == "tertiary_link"  then class = "tertiary"
    elseif hw == "service"                              then class = "service"
    elseif hw == "track"                                then class = "track"
    elseif hw == "footway" or hw == "path" or hw == "cycleway"
        or hw == "pedestrian" or hw == "steps"          then class = "path"
    end
    Layer("transportation", false)
    Attribute("class", class)
    return
  end

  local rw = Find("railway")
  if rw == "rail" or rw == "subway" or rw == "tram" or rw == "light_rail" then
    Layer("transportation", false)
    Attribute("class", "rail")
    return
  end

  -- ── Waterway (linear) ────────────────────────────────────────────────
  local waterway = Find("waterway")
  if waterway == "river" or waterway == "canal" then
    Layer("waterway", false)
    Attribute("class", waterway)
    return
  end
  if waterway == "stream" or waterway == "ditch" then
    Layer("waterway", false)
    Attribute("class", "stream")
    return
  end

  -- ── Water (area) ─────────────────────────────────────────────────────
  local natural  = Find("natural")
  local water    = Find("water")
  local landuse  = Find("landuse")
  if natural == "water" or natural == "bay" or water ~= ""
      or landuse == "reservoir" or landuse == "basin" then
    Layer("water", true)
    Attribute("class", "lake")
    return
  end

  -- ── Landuse ──────────────────────────────────────────────────────────
  local leisure = Find("leisure")
  if landuse == "forest" or landuse == "park" or landuse == "grass"
      or landuse == "meadow" or landuse == "cemetery"
      or landuse == "recreation_ground" then
    Layer("landuse", true)
    Attribute("class", "park")
    return
  end
  if leisure == "park" or leisure == "garden" or leisure == "pitch"
      or leisure == "nature_reserve" then
    Layer("landuse", true)
    Attribute("class", "park")
    return
  end
  if landuse == "residential" then
    Layer("landuse", true)
    Attribute("class", "residential")
    return
  end
  if landuse == "commercial" or landuse == "retail" then
    Layer("landuse", true)
    Attribute("class", "commercial")
    return
  end
  if landuse == "industrial" then
    Layer("landuse", true)
    Attribute("class", "industrial")
    return
  end

  -- ── Building ─────────────────────────────────────────────────────────
  local building = Find("building")
  if building ~= "" and building ~= "no" then
    Layer("building", true)
    return
  end
end

function node_function()
  -- no node processing for basemap
end
