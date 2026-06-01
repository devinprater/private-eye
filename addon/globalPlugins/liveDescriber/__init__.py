from __future__ import annotations

import os
import sys

_addonDir = os.path.dirname(__file__)
_libDir = os.path.join(_addonDir, "lib")
if os.path.isdir(_libDir) and _libDir not in sys.path:
	sys.path.insert(0, _libDir)

import config
import globalPluginHandler
import gui
import gui.settingsDialogs as settingsDialogs
import api
import scriptHandler
import ui
import wx
from gui import guiHelper
from logHandler import log

from .contextManager import DescriptionContext
from .descriptionWorker import DescriptionWorker
from .ollamaClient import DEFAULT_SYSTEM_PROMPT, list_models, normalize_base_url
from .promptModes import (
	PROMPT_MODE_AUTO,
	PROMPT_MODES,
	get_prompt_for_mode,
	select_prompt_mode,
)


DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma4"


config.conf.spec["liveDescriber"] = {
	"ollamaBaseUrl": f'string(default="{DEFAULT_BASE_URL}")',
	"model": f'string(default="{DEFAULT_MODEL}")',
	"promptMode": f'string(default="{PROMPT_MODE_AUTO}")',
	"systemPrompt": f'string(default="{DEFAULT_SYSTEM_PROMPT}")',
	"interval": "float(default=4.0, min=2.0, max=15.0)",
	"requestTimeout": "float(default=60.0, min=10.0, max=180.0)",
	"maxContextEntries": "integer(default=8, min=3, max=12)",
	"captureRegionEnabled": "boolean(default=False)",
	"captureRegionX": "integer(default=0, min=0)",
	"captureRegionY": "integer(default=0, min=0)",
	"captureRegionWidth": "integer(default=1280, min=1)",
	"captureRegionHeight": "integer(default=720, min=1)",
}


def _settings():
	return config.conf["liveDescriber"]


def _addLabeledItem(sHelper, parent, label, item):
	labelCtrl = wx.StaticText(parent, label=label)
	item.SetName(label)
	try:
		item.SetLabel(label)
	except AttributeError:
		pass
	labelCtrl.SetName(label)
	labelCtrl.SetLabel(label)
	row = wx.BoxSizer(wx.HORIZONTAL)
	row.Add(labelCtrl, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL)
	row.Add(item, flag=wx.EXPAND, proportion=1)
	sHelper.addItem(row)
	return item


def _getFloatFromText(ctrl, option, minimum, maximum):
	value = ctrl.GetValue().strip()
	try:
		number = float(value)
	except ValueError:
		raise ValueError(f"{option} must be a number.")
	if number < minimum or number > maximum:
		raise ValueError(f"{option} must be between {minimum:g} and {maximum:g}.")
	return number


def _getIntFromText(ctrl, option, minimum, maximum):
	value = ctrl.GetValue().strip()
	try:
		number = int(value)
	except ValueError:
		raise ValueError(f"{option} must be a whole number.")
	if number < minimum or number > maximum:
		raise ValueError(f"{option} must be between {minimum} and {maximum}.")
	return number


class LiveDescriberSettingsPanel(settingsDialogs.SettingsPanel):
	title = "Private Eye"

	def makeSettings(self, settingsSizer):
		settings = _settings()
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		self.baseUrlCtrl = sHelper.addLabeledControl("Ollama server URL", wx.TextCtrl, value=settings["ollamaBaseUrl"])
		self.modelChoice = sHelper.addLabeledControl("Model", wx.ComboBox, style=wx.CB_DROPDOWN)
		self.promptModeChoice = sHelper.addLabeledControl("Prompt mode", wx.Choice, choices=PROMPT_MODES)
		promptMode = settings["promptMode"]
		self.promptModeChoice.SetStringSelection(promptMode if promptMode in PROMPT_MODES else PROMPT_MODE_AUTO)
		self.systemPromptCtrl = sHelper.addLabeledControl(
			"General system prompt",
			wx.TextCtrl,
			value=settings["systemPrompt"],
			style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
		)
		self.systemPromptCtrl.SetMinSize((500, 120))
		self.refreshButton = wx.Button(self, label="Refresh/Test Models")
		self.refreshButton.Bind(wx.EVT_BUTTON, self.onRefreshModels)
		sHelper.addItem(self.refreshButton)
		self.statusText = sHelper.addItem(wx.StaticText(self, label=""))

		self.intervalCtrl = sHelper.addLabeledControl(
			"Capture interval in seconds",
			wx.TextCtrl,
			value=str(float(settings["interval"])),
		)
		self.contextDepthCtrl = sHelper.addLabeledControl(
			"Context depth",
			wx.TextCtrl,
			value=str(int(settings["maxContextEntries"])),
		)
		self.requestTimeoutCtrl = sHelper.addLabeledControl(
			"Ollama timeout in seconds",
			wx.TextCtrl,
			value=str(float(settings["requestTimeout"])),
		)
		self.regionEnabledCtrl = sHelper.addItem(wx.CheckBox(self, label="Capture a fixed screen region"))
		self.regionEnabledCtrl.SetValue(bool(settings["captureRegionEnabled"]))
		self.regionXCtrl = sHelper.addLabeledControl("Region X", wx.TextCtrl, value=str(int(settings["captureRegionX"])))
		self.regionYCtrl = sHelper.addLabeledControl("Region Y", wx.TextCtrl, value=str(int(settings["captureRegionY"])))
		self.regionWidthCtrl = sHelper.addLabeledControl("Region width", wx.TextCtrl, value=str(int(settings["captureRegionWidth"])))
		self.regionHeightCtrl = sHelper.addLabeledControl("Region height", wx.TextCtrl, value=str(int(settings["captureRegionHeight"])))

		self._loadModelsOnOpen()

	def _populateModels(self, models, savedModel):
		values = sorted(set(models))
		if savedModel and savedModel not in values:
			values.insert(0, savedModel)
		self.modelChoice.Clear()
		for value in values or [savedModel or DEFAULT_MODEL]:
			self.modelChoice.Append(value)
		self.modelChoice.SetValue(savedModel or (values[0] if values else DEFAULT_MODEL))

	def _loadModelsOnOpen(self):
		savedModel = _settings()["model"]
		try:
			models = list_models(self.baseUrlCtrl.GetValue(), timeout=5)
			self._populateModels(models, savedModel)
			self.statusText.SetLabel(f"Loaded {len(models)} model(s).")
		except Exception as e:
			log.warning(f"Private Eye could not load Ollama models: {e}", exc_info=True)
			self._populateModels([], savedModel)
			self.statusText.SetLabel("Could not reach the Ollama server.")

	def onRefreshModels(self, evt):
		try:
			baseUrl = normalize_base_url(self.baseUrlCtrl.GetValue())
			models = list_models(baseUrl, timeout=5)
			self.baseUrlCtrl.SetValue(baseUrl)
			self._populateModels(models, self.modelChoice.GetValue())
			self.statusText.SetLabel(f"Connected. Loaded {len(models)} model(s).")
			ui.message("Ollama connection successful")
		except Exception as e:
			log.warning(f"Private Eye model refresh failed: {e}", exc_info=True)
			self._populateModels([], self.modelChoice.GetValue() or _settings()["model"])
			self.statusText.SetLabel("Connection failed. Check the server URL.")
			ui.message("Ollama connection failed")

	def isValid(self):
		try:
			_getFloatFromText(self.intervalCtrl, "Capture interval in seconds", 2.0, 15.0)
		except ValueError as e:
			self._validationErrorMessageBox(str(e), "Capture interval in seconds")
			return False
		try:
			_getFloatFromText(self.requestTimeoutCtrl, "Ollama timeout in seconds", 10.0, 180.0)
		except ValueError as e:
			self._validationErrorMessageBox(str(e), "Ollama timeout in seconds")
			return False
		intFields = (
			(self.contextDepthCtrl, "Context depth", 3, 12),
			(self.regionXCtrl, "Region X", 0, 100000),
			(self.regionYCtrl, "Region Y", 0, 100000),
			(self.regionWidthCtrl, "Region width", 1, 100000),
			(self.regionHeightCtrl, "Region height", 1, 100000),
		)
		for ctrl, option, minimum, maximum in intFields:
			try:
				_getIntFromText(ctrl, option, minimum, maximum)
			except ValueError as e:
				self._validationErrorMessageBox(str(e), option)
				return False
		if not self.modelChoice.GetValue().strip():
			self._validationErrorMessageBox("Private Eye model cannot be empty.", "Model")
			return False
		if not self.systemPromptCtrl.GetValue().strip():
			self._validationErrorMessageBox("General system prompt cannot be empty.", "General system prompt")
			return False
		return True

	def onSave(self):
		model = self.modelChoice.GetValue().strip()
		if not model:
			raise ValueError("Private Eye model cannot be empty.")
		systemPrompt = self.systemPromptCtrl.GetValue().strip()
		if not systemPrompt:
			raise ValueError("General system prompt cannot be empty.")
		settings = _settings()
		settings["ollamaBaseUrl"] = normalize_base_url(self.baseUrlCtrl.GetValue())
		settings["model"] = model
		settings["promptMode"] = self.promptModeChoice.GetStringSelection() or PROMPT_MODE_AUTO
		settings["systemPrompt"] = systemPrompt
		settings["interval"] = _getFloatFromText(self.intervalCtrl, "Capture interval in seconds", 2.0, 15.0)
		settings["requestTimeout"] = _getFloatFromText(self.requestTimeoutCtrl, "Ollama timeout in seconds", 10.0, 180.0)
		settings["maxContextEntries"] = _getIntFromText(self.contextDepthCtrl, "Context depth", 3, 12)
		settings["captureRegionEnabled"] = bool(self.regionEnabledCtrl.GetValue())
		settings["captureRegionX"] = _getIntFromText(self.regionXCtrl, "Region X", 0, 100000)
		settings["captureRegionY"] = _getIntFromText(self.regionYCtrl, "Region Y", 0, 100000)
		settings["captureRegionWidth"] = _getIntFromText(self.regionWidthCtrl, "Region width", 1, 100000)
		settings["captureRegionHeight"] = _getIntFromText(self.regionHeightCtrl, "Region height", 1, 100000)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self._context = DescriptionContext(max_entries=int(_settings()["maxContextEntries"]))
		self._worker = None
		self._registerSettingsPanel()

	def terminate(self):
		self._stopWorker()
		self._unregisterSettingsPanel()

	def _registerSettingsPanel(self):
		if LiveDescriberSettingsPanel not in settingsDialogs.NVDASettingsDialog.categoryClasses:
			settingsDialogs.NVDASettingsDialog.categoryClasses.append(LiveDescriberSettingsPanel)
			log.debug("Private Eye settings panel registered")

	def _unregisterSettingsPanel(self):
		while LiveDescriberSettingsPanel in settingsDialogs.NVDASettingsDialog.categoryClasses:
			settingsDialogs.NVDASettingsDialog.categoryClasses.remove(LiveDescriberSettingsPanel)

	def _makeWorker(self):
		settings = _settings()
		self._context.max_entries = int(settings["maxContextEntries"])
		windowTitle = self._getForegroundWindowTitle()
		effectiveMode = select_prompt_mode(settings["promptMode"], windowTitle)
		systemPrompt = get_prompt_for_mode(effectiveMode, settings["systemPrompt"])
		log.debug(f"Private Eye using {effectiveMode} prompt mode for foreground window: {windowTitle!r}")
		return DescriptionWorker(
			base_url=settings["ollamaBaseUrl"],
			model=settings["model"],
			interval=float(settings["interval"]),
			request_timeout=float(settings["requestTimeout"]),
			system_prompt=systemPrompt,
			context=self._context,
			region=self._getRegion(settings),
		)

	def _getForegroundWindowTitle(self):
		try:
			obj = api.getForegroundObject()
			return obj.name or getattr(obj.appModule, "appName", "") or ""
		except Exception as e:
			log.debugWarning(f"Private Eye could not get foreground window title: {e}")
			return ""

	def _getRegion(self, settings):
		if not settings["captureRegionEnabled"]:
			return None
		return {
			"left": int(settings["captureRegionX"]),
			"top": int(settings["captureRegionY"]),
			"width": int(settings["captureRegionWidth"]),
			"height": int(settings["captureRegionHeight"]),
		}

	def _stopWorker(self):
		if self._worker:
			self._worker.stop()
			self._worker.join(timeout=3)
			self._worker = None

	@scriptHandler.script(description="Toggle Private Eye", gesture="kb:NVDA+alt+v")
	def script_toggleLiveDescription(self, gesture):
		if self._worker and self._worker.is_alive():
			self._stopWorker()
			ui.message("Private Eye stopped")
			return
		self._worker = self._makeWorker()
		self._worker.start()
		ui.message("Private Eye started")

	@scriptHandler.script(description="Clear Private Eye context", gesture="kb:NVDA+shift+alt+v")
	def script_clearContext(self, gesture):
		wasRunning = self._worker and self._worker.is_alive()
		if wasRunning:
			self._stopWorker()
		self._context.clear()
		if wasRunning:
			self._worker = self._makeWorker()
			self._worker.start()
		ui.message("Private Eye context cleared")

	@scriptHandler.script(description="Open Private Eye settings", gesture="kb:NVDA+control+alt+v")
	def script_openSettings(self, gesture):
		self._registerSettingsPanel()
		openSettingsDialog = getattr(gui.mainFrame, "popupSettingsDialog", None)
		if openSettingsDialog is None:
			openSettingsDialog = getattr(gui.mainFrame, "_popupSettingsDialog")
		wx.CallAfter(openSettingsDialog, settingsDialogs.NVDASettingsDialog, LiveDescriberSettingsPanel)
