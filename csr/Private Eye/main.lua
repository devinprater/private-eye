require "import"

import "android.accessibilityservice.AccessibilityService"
import "android.app.AlertDialog"
import "android.content.Context"
import "android.graphics.Bitmap"
import "android.os.Handler"
import "android.os.Looper"
import "android.util.Base64"
import "android.util.Log"
import "android.view.WindowManager"
import "android.widget.EditText"
import "android.widget.LinearLayout"
import "android.widget.Spinner"
import "android.widget.ArrayAdapter"
import "java.io.ByteArrayOutputStream"
import "java.util.concurrent.Executor"
import "org.json.JSONArray"
import "org.json.JSONObject"

local PREFS_NAME = "PrivateEyePrefs"
local DEFAULT_PRIMARY_URL = "http://127.0.0.1:11434"
local DEFAULT_FALLBACK_URL = ""
local DEFAULT_MODEL = "gemma4:31b-cloud"
local DEFAULT_INTERVAL = 4
local DEFAULT_TIMEOUT = 60
local DEFAULT_CONTEXT_DEPTH = 8
local MAX_IMAGE_WIDTH = 1280
local MAX_IMAGE_HEIGHT = 720
local JPEG_QUALITY = 75
local ERROR_SPEAK_INTERVAL = 60
local TICK_MS = 500

local PROMPT_MODES = {"Automatic", "General", "Video", "Game"}

local GENERAL_PROMPT = table.concat({
  "You are describing live screen content for a blind Android user. ",
  "Be concise and focus on meaningful visual changes. Read important on-screen text. ",
  "Maintain continuity across frames by reusing short labels for recurring people, objects, menus, and places. ",
  "If the frame has not meaningfully changed, respond exactly with [NO CHANGE].",
})

local VIDEO_PROMPT = table.concat({
  "You are providing audio description for a blind viewer. ",
  "Describe important visual information not conveyed by dialogue or sound: setting, scene changes, actions, ",
  "characters, facial expressions, costumes, on-screen text, and visual jokes or reveals. ",
  "Use present tense, one concise sentence, and prioritize what matters to understanding the story. ",
  "Maintain continuity by reusing previously established short labels for recurring characters, objects, and places. ",
  "Describe what changed instead of reintroducing the same subject. Do not speculate beyond visible evidence. ",
  "If the frame has not meaningfully changed, respond exactly with [NO CHANGE].",
})

local GAME_PROMPT = table.concat({
  "You are describing a game screen for a blind player. ",
  "Prioritize playable information: menu text and selected item, current area, hazards, enemies, pathways, doors, ",
  "objectives, interactable objects, characters, and directions using left/right/above/below/center and approximate distance. ",
  "Maintain continuity by reusing previously established names for menus, areas, characters, enemies, objects, and hazards. ",
  "Describe what changed or what is newly actionable instead of repeating known details. Keep the response short and actionable. ",
  "If the frame has not meaningfully changed, respond exactly with [NO CHANGE].",
})

local prefs = service.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
local handler = Handler(Looper.getMainLooper())
local state = _G.__private_eye_state or {
  running = false,
  busy = false,
  ticker = nil,
  nextCaptureAt = 0,
  activeUrl = nil,
  activePackage = "",
  context = {},
  lastErrorAt = 0,
  session = 0,
  captures = 0,
  requests = 0,
  replies = 0,
  noChanges = 0,
  lastStatus = "not started",
}
_G.__private_eye_state = state
state.running = state.running or false
state.busy = state.busy or false
state.nextCaptureAt = state.nextCaptureAt or 0
state.activePackage = state.activePackage or ""
state.context = state.context or {}
state.lastErrorAt = state.lastErrorAt or 0
state.session = state.session or 0
state.captures = state.captures or 0
state.requests = state.requests or 0
state.replies = state.replies or 0
state.noChanges = state.noChanges or 0
state.lastStatus = state.lastStatus or "not started"

local function trim(value)
  if value == nil then
    return ""
  end
  return tostring(value):gsub("^%s+", ""):gsub("%s+$", "")
end

local function debug(message)
  state.lastStatus = trim(message)
  Log.d("PrivateEye", state.lastStatus)
end

local function safe(callable, fallback)
  local ok, result = pcall(callable)
  if ok then
    return result
  end
  return fallback
end

local function proxy(className, methods)
  return luajava.createProxy(className, methods)
end

local function post(callable)
  handler.post(proxy("java.lang.Runnable", {run = callable}))
end

local function speak(message)
  local value = trim(message)
  if value ~= "" then
    post(function() service.speak(value) end)
  end
end

local function speakAfterCurrent(message)
  local value = trim(message)
  if value ~= "" then
    post(function() service.appendSpeak(value) end)
  end
end

local function reportError(message)
  debug("error: " .. message)
  local now = os.time()
  if now - state.lastErrorAt >= ERROR_SPEAK_INTERVAL then
    state.lastErrorAt = now
    speak("Private Eye " .. message)
  end
end

local function normalizeUrl(value)
  local url = trim(value)
  if url == "" then
    return ""
  end
  if not url:match("^https?://") then
    url = "http://" .. url
  end
  return url:gsub("/+$", "")
end

local function settings()
  return {
    primaryUrl = normalizeUrl(prefs.getString("primaryUrl", DEFAULT_PRIMARY_URL)),
    fallbackUrl = normalizeUrl(prefs.getString("fallbackUrl", DEFAULT_FALLBACK_URL)),
    model = trim(prefs.getString("model", DEFAULT_MODEL)),
    interval = tonumber(prefs.getString("interval", tostring(DEFAULT_INTERVAL))) or DEFAULT_INTERVAL,
    timeout = tonumber(prefs.getString("timeout", tostring(DEFAULT_TIMEOUT))) or DEFAULT_TIMEOUT,
    contextDepth = tonumber(prefs.getString("contextDepth", tostring(DEFAULT_CONTEXT_DEPTH))) or DEFAULT_CONTEXT_DEPTH,
    promptMode = prefs.getString("promptMode", PROMPT_MODES[1]),
  }
end

local function saveSettings(values)
  local editor = prefs.edit()
  editor.putString("primaryUrl", normalizeUrl(values.primaryUrl))
  editor.putString("fallbackUrl", normalizeUrl(values.fallbackUrl))
  editor.putString("model", trim(values.model))
  editor.putString("interval", tostring(values.interval))
  editor.putString("timeout", tostring(values.timeout))
  editor.putString("contextDepth", tostring(values.contextDepth))
  editor.putString("promptMode", values.promptMode)
  editor.apply()
  state.activeUrl = nil
end

local function clearContext(announce)
  state.context = {}
  if announce then
    speak("Private Eye context cleared")
  end
end

local function addContext(description, depth)
  state.context[#state.context + 1] = {
    time = os.date("%H:%M:%S"),
    text = description,
  }
  while #state.context > depth do
    table.remove(state.context, 1)
  end
end

local function formatContext()
  if #state.context == 0 then
    return "Continuity context: no previous descriptions yet. Introduce important visible people, objects, places, and text briefly."
  end
  local lines = {"Continuity context from recent frames, oldest to newest:"}
  for _, entry in ipairs(state.context) do
    lines[#lines + 1] = "- " .. entry.time .. ": " .. entry.text
  end
  lines[#lines + 1] = "Use this context for continuity. Describe only meaningful new visual information or changes."
  return table.concat(lines, "\n")
end

local function packageName()
  local root = safe(function() return service.getRootInActiveWindow() end)
  return trim(safe(function() return root.getPackageName() end, ""))
end

local function containsAny(value, patterns)
  for _, pattern in ipairs(patterns) do
    if value:find(pattern, 1, true) then
      return true
    end
  end
  return false
end

local function effectivePrompt(configuredMode, appPackage)
  local mode = configuredMode
  if mode == "Automatic" then
    local name = appPackage:lower()
    if containsAny(name, {"youtube", "netflix", "hulu", "disney", "primevideo", "twitch", "crunchyroll", "plex", "jellyfin"}) then
      mode = "Video"
    elseif containsAny(name, {"ppsspp", "retroarch", "dolphin", "duckstation", "dosbox", "mame", "melonds", "mgba", "game"}) then
      mode = "Game"
    else
      mode = "General"
    end
  end
  if mode == "Video" then
    return VIDEO_PROMPT
  end
  if mode == "Game" then
    return GAME_PROMPT
  end
  return GENERAL_PROMPT
end

local function isolatedRequest(config, path, method, body, callback)
  task(function(primaryUrl, fallbackUrl, activeUrl, requestPath, requestMethod, requestBody, timeoutSeconds)
    require "import"
    import "java.io.BufferedReader"
    import "java.io.InputStreamReader"
    import "java.lang.String"
    import "java.net.URL"

    local function readStream(stream)
      local reader = BufferedReader(InputStreamReader(stream))
      local parts = {}
      while true do
        local line = reader.readLine()
        if line == nil then
          break
        end
        parts[#parts + 1] = tostring(line)
      end
      reader.close()
      return table.concat(parts, "\n")
    end

    local function add(candidates, value)
      if value == nil or value == "" then
        return
      end
      for _, existing in ipairs(candidates) do
        if existing == value then
          return
        end
      end
      candidates[#candidates + 1] = value
    end

    local candidates = {}
    add(candidates, activeUrl)
    add(candidates, primaryUrl)
    add(candidates, fallbackUrl)
    local lastError = "no Ollama URL configured"
    for _, baseUrl in ipairs(candidates) do
      local ok, result = pcall(function()
        local connection = URL(baseUrl .. requestPath).openConnection()
        connection.setConnectTimeout(math.floor(math.min(timeoutSeconds, 5) * 1000))
        connection.setReadTimeout(math.floor(timeoutSeconds * 1000))
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("User-Agent", "PrivateEye-Commentary/1.0")
        connection.setRequestMethod(requestMethod)
        if requestBody ~= nil and requestBody ~= "" then
          local bytes = String(requestBody).getBytes("UTF-8")
          connection.setDoOutput(true)
          connection.setRequestProperty("Content-Type", "application/json")
          connection.setRequestProperty("Content-Length", tostring(#bytes))
          local output = connection.getOutputStream()
          output.write(bytes)
          output.flush()
          output.close()
        end
        local status = connection.getResponseCode()
        local stream = status >= 200 and status < 300 and connection.getInputStream() or connection.getErrorStream()
        local response = stream ~= nil and readStream(stream) or ""
        connection.disconnect()
        if status < 200 or status >= 300 then
          error("HTTP " .. status .. (response ~= "" and ": " .. response or ""))
        end
        return response
      end)
      if ok then
        return "ok", result, baseUrl
      end
      lastError = tostring(result)
    end
    return "error", lastError, ""
  end, config.primaryUrl, config.fallbackUrl, state.activeUrl or "", path, method, body or "", config.timeout, callback)
end

local function describeImage(imageBase64, appPackage, session)
  local config = settings()
  state.requests = state.requests + 1
  debug("request " .. state.requests .. " started for " .. appPackage)
  local payload = JSONObject()
  payload.put("model", config.model)
  payload.put("stream", false)
  payload.put("system", effectivePrompt(config.promptMode, appPackage))
  payload.put("prompt", formatContext() .. "\n\nDescribe the current frame in one short sentence. Do not repeat details already established unless they changed. Only mention visible details that matter right now.")
  payload.put("images", JSONArray().put(imageBase64))
  payload.put("options", JSONObject().put("num_predict", 80).put("temperature", 0.3))
  isolatedRequest(config, "/api/generate", "POST", tostring(payload), function(status, raw, activeUrl)
    state.busy = false
    if status ~= "ok" then
      reportError("request failed: " .. trim(raw))
      return
    end
    state.activeUrl = activeUrl
    local description = trim(JSONObject(raw).optString("response", ""))
    if state.running and state.session == session and description ~= "" and description ~= "[NO CHANGE]" then
      state.replies = state.replies + 1
      debug("reply " .. state.replies .. ": " .. description)
      addContext(description, config.contextDepth)
      speakAfterCurrent(description)
    elseif state.running and state.session == session and description == "[NO CHANGE]" then
      state.noChanges = state.noChanges + 1
      debug("no change " .. state.noChanges)
    else
      debug("reply ignored because the session stopped or the response was empty")
    end
  end)
end

local function encodeScreenshot(result)
  local buffer = result.getHardwareBuffer()
  local hardwareBitmap = Bitmap.wrapHardwareBuffer(buffer, result.getColorSpace())
  if hardwareBitmap == nil then
    buffer.close()
    error("could not decode screenshot")
  end
  local bitmap = hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false)
  buffer.close()
  local width = bitmap.getWidth()
  local height = bitmap.getHeight()
  local scale = math.min(1, MAX_IMAGE_WIDTH / width, MAX_IMAGE_HEIGHT / height)
  if scale < 1 then
    local resized = Bitmap.createScaledBitmap(bitmap, math.floor(width * scale), math.floor(height * scale), true)
    bitmap.recycle()
    bitmap = resized
  end
  local output = ByteArrayOutputStream()
  bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output)
  bitmap.recycle()
  local encoded = Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP)
  output.close()
  return tostring(encoded)
end

local directExecutor = proxy("java.util.concurrent.Executor", {
  execute = function(command) command.run() end,
})

local function capture()
  state.busy = true
  local session = state.session
  state.captures = state.captures + 1
  debug("capture " .. state.captures .. " started")
  local callback = proxy("android.accessibilityservice.AccessibilityService$TakeScreenshotCallback", {
    onSuccess = function(result)
      debug("capture " .. state.captures .. " completed")
      local ok, imageOrProblem = pcall(encodeScreenshot, result)
      if not ok then
        state.busy = false
        reportError("could not encode screenshot: " .. trim(imageOrProblem))
        return
      end
      describeImage(imageOrProblem, state.activePackage, session)
    end,
    onFailure = function(errorCode)
      state.busy = false
      reportError("could not capture the screen, error " .. tostring(errorCode))
    end,
  })
  local ok, problem = pcall(function()
    service.takeScreenshot(0, directExecutor, callback)
  end)
  if not ok then
    state.busy = false
    reportError("could not start screen capture: " .. trim(problem))
  end
end

local function poll()
  if not state.running or state.busy then
    return
  end
  local now = os.time()
  if now < state.nextCaptureAt then
    return
  end
  state.nextCaptureAt = now + settings().interval
  local appPackage = packageName()
  if appPackage == "com.nirenr.talkman" then
    debug("capture paused while Commentary is foreground")
    return
  end
  if appPackage ~= state.activePackage then
    state.activePackage = appPackage
    clearContext(false)
  end
  capture()
end

local function start()
  if state.running then
    speak("Private Eye is already running")
    return
  end
  state.running = true
  state.session = state.session + 1
  state.nextCaptureAt = 0
  state.activePackage = packageName()
  debug("started for " .. state.activePackage)
  if state.ticker == nil or not safe(function() return state.ticker.isRun() end, false) then
    state.ticker = service.ticker(function() safe(poll) end, TICK_MS)
  end
  speak("Private Eye started")
end

local function stop()
  state.running = false
  state.session = state.session + 1
  if state.ticker ~= nil then
    safe(function() state.ticker.stop() end)
    state.ticker = nil
  end
  debug("stopped")
  speak("Private Eye stopped")
end

local function showOverlay(dialog)
  local window = dialog.getWindow()
  window.setType(WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY)
  dialog.show()
end

local function field(layout, hint, value)
  local input = EditText(service)
  input.setHint(hint)
  input.setText(tostring(value))
  layout.addView(input)
  return input
end

local function validNumber(value, minimum, maximum)
  local number = tonumber(trim(value))
  return number ~= nil and number >= minimum and number <= maximum and number
end

local function showSettings()
  local config = settings()
  local layout = LinearLayout(service)
  layout.setOrientation(LinearLayout.VERTICAL)
  layout.setPadding(32, 16, 32, 16)
  local primary = field(layout, "Primary Ollama URL", config.primaryUrl)
  local fallback = field(layout, "Fallback Ollama URL", config.fallbackUrl)
  local model = field(layout, "Model", config.model)
  local interval = field(layout, "Capture interval in seconds", config.interval)
  local timeout = field(layout, "Request timeout in seconds", config.timeout)
  local depth = field(layout, "Context depth", config.contextDepth)
  local mode = Spinner(service)
  local adapter = ArrayAdapter(service, android.R.layout.simple_spinner_item, PROMPT_MODES)
  adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
  mode.setAdapter(adapter)
  for index, value in ipairs(PROMPT_MODES) do
    if value == config.promptMode then
      mode.setSelection(index - 1)
    end
  end
  layout.addView(mode)
  local dialog
  local builder = AlertDialog.Builder(service)
  builder.setTitle("Private Eye settings")
  builder.setView(layout)
  builder.setPositiveButton("Save", proxy("android.content.DialogInterface$OnClickListener", {
      onClick = function()
        local intervalValue = validNumber(interval.getText(), 2, 60)
        local timeoutValue = validNumber(timeout.getText(), 5, 300)
        local depthValue = validNumber(depth.getText(), 1, 20)
        if trim(primary.getText()) == "" or trim(model.getText()) == "" or not intervalValue or not timeoutValue or not depthValue then
          speak("Private Eye settings were not saved. Check the values.")
          return
        end
        saveSettings({
          primaryUrl = primary.getText(),
          fallbackUrl = fallback.getText(),
          model = model.getText(),
          interval = intervalValue,
          timeout = timeoutValue,
          contextDepth = math.floor(depthValue),
          promptMode = tostring(mode.getSelectedItem()),
        })
        speak("Private Eye settings saved")
      end,
    }))
  builder.setNegativeButton("Cancel", nil)
  dialog = builder.create()
  showOverlay(dialog)
end

local function testConnection()
  if state.busy then
    speak("Private Eye is busy")
    return
  end
  state.busy = true
  speak("Testing Private Eye connection")
  local config = settings()
  config.timeout = math.min(config.timeout, 10)
  isolatedRequest(config, "/api/tags", "GET", nil, function(status, raw, activeUrl)
    state.busy = false
    if status ~= "ok" then
      reportError("connection test failed: " .. trim(raw))
      return
    end
    state.activeUrl = activeUrl
    local models = JSONObject(raw).optJSONArray("models")
    local found = false
    if models ~= nil then
      for index = 0, models.length() - 1 do
        if tostring(models.getJSONObject(index).optString("name", "")) == config.model then
          found = true
        end
      end
    end
    if found then
      speak("Private Eye connected. Model " .. config.model .. " is available.")
    else
      speak("Private Eye connected, but model " .. config.model .. " was not found.")
    end
  end)
end

local function speakStatus()
  local message = state.running and "running" or "stopped"
  message = "Private Eye " .. message
    .. ". Captures " .. state.captures
    .. ". Requests " .. state.requests
    .. ". Replies " .. state.replies
    .. ". No changes " .. state.noChanges
    .. ". Last status: " .. state.lastStatus
  speak(message)
end

local function showMenu()
  local items = {
    state.running and "Stop" or "Start",
    "Clear context",
    "Settings",
    "Test connection",
    "Status",
  }
  local builder = AlertDialog.Builder(service)
  builder.setTitle("Private Eye")
  builder.setItems(items, proxy("android.content.DialogInterface$OnClickListener", {
      onClick = function(_, which)
        if which == 0 then
          if state.running then stop() else start() end
        elseif which == 1 then
          clearContext(true)
        elseif which == 2 then
          showSettings()
        elseif which == 3 then
          testConnection()
        elseif which == 4 then
          speakStatus()
        end
      end,
    }))
  builder.setNegativeButton("Cancel", nil)
  local dialog = builder.create()
  showOverlay(dialog)
end

if state.running then
  stop()
else
  showMenu()
end
