-- Hermes 2.0 basemap — minimal tilemaker process
-- Layers: transportation, waterway, water, landuse, building
-- No Natural Earth dependency (zoom 8-14 city level)

function way_function(w)
  local t = w:tags()

  -- ── Transportation ────────────────────────────────────────────────────
  local hw = t["highway"]
  if hw ~= nil then
    local class = "minor"
    if hw == "motorway" or hw == "motorway_link" then
      class = "motorway"
    elseif hw == "trunk" or hw == "trunk_link" then
      class = "trunk"
    elseif hw == "primary" or hw == "primary_link" then
      class = "primary"
    elseif hw == "secondary" or hw == "secondary_link" then
      class = "secondary"
    elseif hw == "tertiary" or hw == "tertiary_link" then
      class = "tertiary"
    elseif hw == "unclassified" or hw == "residential" then
      class = "minor"
    elseif hw == "service" then
      class = "service"
    elseif hw == "track" then
      class = "track"
    elseif hw == "footway" or hw == "path" or hw == "cycleway"
        or hw == "pedestrian" or hw == "steps" then
      class = "path"
    end
    w:Layer("transportation", false)
    w:Attribute("class", class)
    return
  end

  local rw = t["railway"]
  if rw == "rail" or rw == "subway" or rw == "tram" or rw == "light_rail" then
    w:Layer("transportation", false)
    w:Attribute("class", "rail")
    return
  end

  -- ── Waterway (linear) ────────────────────────────────────────────────
  local waterway = t["waterway"]
  if waterway == "river" or waterway == "canal" then
    w:Layer("waterway", false)
    w:Attribute("class", waterway)
    return
  end
  if waterway == "stream" or waterway == "ditch" then
    w:Layer("waterway", false)
    w:Attribute("class", "stream")
    return
  end

  -- ── Water (area) ─────────────────────────────────────────────────────
  local natural = t["natural"]
  local water   = t["water"]
  local landuse = t["landuse"]
  if natural == "water" or natural == "bay" or water ~= nil
      or landuse == "reservoir" or landuse == "basin" then
    w:Layer("water", true)
    w:Attribute("class", "lake")
    return
  end

  -- ── Landuse ──────────────────────────────────────────────────────────
  local leisure = t["leisure"]
  if landuse == "forest" or landuse == "park" or landuse == "grass"
      or landuse == "meadow" or landuse == "cemetery"
      or landuse == "recreation_ground" then
    w:Layer("landuse", true)
    w:Attribute("class", "park")
    return
  end
  if leisure == "park" or leisure == "garden" or leisure == "pitch"
      or leisure == "nature_reserve" then
    w:Layer("landuse", true)
    w:Attribute("class", "park")
    return
  end
  if landuse == "residential" then
    w:Layer("landuse", true)
    w:Attribute("class", "residential")
    return
  end
  if landuse == "commercial" or landuse == "retail" then
    w:Layer("landuse", true)
    w:Attribute("class", "commercial")
    return
  end
  if landuse == "industrial" then
    w:Layer("landuse", true)
    w:Attribute("class", "industrial")
    return
  end

  -- ── Building ─────────────────────────────────────────────────────────
  local building = t["building"]
  if building ~= nil and building ~= "no" then
    w:Layer("building", true)
    return
  end
end

function node_function(n)
  -- No node processing for basemap
end

function relation_function(r)
  -- No relation processing for basemap
end
