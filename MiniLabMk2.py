from __future__ import absolute_import, print_function, unicode_literals
from builtins import range
from functools import partial
import logging
from _Framework import Task
from _Framework.ButtonMatrixElement import ButtonMatrixElement
from _Framework.ButtonElement import ButtonElement
from _Framework.DeviceComponent import DeviceComponent
from _Framework.EncoderElement import EncoderElement
from _Framework.InputControlElement import MIDI_CC_TYPE
from _Framework.Layer import Layer
from _Framework.SliderElement import SliderElement
from _Framework.SubjectSlot import subject_slot
from _Framework.SysexValueControl import SysexValueControl
from _Arturia.ArturiaControlSurface import COLOR_PROPERTY, LIVE_MODE_MSG_HEAD, LOAD_MEMORY_COMMAND, MEMORY_SLOT_PROPERTY, OFF_VALUE, SETUP_MSG_PREFIX, SETUP_MSG_SUFFIX, STORE_IN_MEMORY_COMMAND, WORKING_MEMORY_ID, WRITE_COMMAND, split_list
import MiniLab.MiniLab as MiniLab
from .HardwareSettingsComponent import HardwareSettingsComponent
from .SessionComponent import SessionComponent
ANALOG_LAB_MEMORY_SLOT_ID = 1 # Remove later
RELATIVE_TWO_COMPLEMENT = 2
LIVE_MEMORY_SLOT_ID = 8
logger = logging.getLogger(__name__)

# enc. 1 - 8: 22-29 
# enc. 9-16: 30, 31, 33, 34, 52, 53, 54, 55 
# enc 1 +shift: 24, 
# enc 9 +shift: 25 (absolute control) 
# enc 1 push: 26, 
# enc 9 push: 27 (switched toggle setting) all others are set to control, relative. channel 2 pads are set to ch11, but standard midi notes


class MiniLabMk2(MiniLab):
    session_component_type = SessionComponent
    encoder_msg_channel = 1
    pad_channel = 10

    def __init__(self, *a, **k):
        super(MiniLabMk2, self).__init__(*a, **k)
        with self.component_guard():
            self._create_hardware_settings()
            self._create_device_row1()

    def _create_controls(self):
        # call base so _device_controls exists
        super(MiniLabMk2, self)._create_controls()
        
        # CCs we want to reclaim
        custom_ccs = [22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 33, 34, 52, 53, 54, 55]

        # Unbind any existing control assigned to these CCs
        for control in getattr(self, "_device_controls", []):
            if hasattr(control, "message_identifier") and control.message_identifier in custom_ccs:
                control.release_parameter()

    def _create_device_row1(self):
        """
        Row 1 (Enc 1–8) → Macros 1–8 of device in memory slot 8
        Enc 1 Push → Reset macros
        Always follows selected track, slot 8 only
        """
        track = self.song().view.selected_track  # always selected track
        try:
            device = track.devices[7]  # memory slot 8
        except IndexError:
            logger.warning(f"Selected track '{track.name}' does not have a device in memory slot 8")
            device = None

        self._device_row1 = DeviceComponent(name="Device_Row1", is_enabled=True)
        if device:
            self._device_row1.set_device(device)

            self._row1_encoders = []
            for i, cc in enumerate(range(22, 30)):
                encoder = EncoderElement(MIDI_CC_TYPE, 2, cc, EncoderElement.RELATIVE_TWO_COMPLEMENT)
                self._device_row1.parameters[i].set_control_element(encoder)
                self._row1_encoders.append(encoder)

            # Enc 1 Push → Reset first 8 macros
            self._row1_reset_button = ButtonElement(True, MIDI_CC_TYPE, 2, 26)
            self._row1_reset_button.add_value_listener(self._reset_row1_macros)

    def _reset_row1_macros(self, value):
        """Resets Row 1 macros to default when push pressed"""
        if value != 0:
            for param in self._device_row1.parameters[:8]:
                param.value = param.default_value

    def _create_hardware_settings(self):
        self._hardware_settings = HardwareSettingsComponent(name="Hardware_Settings",
          is_enabled=False)

    def _create_session(self):
        super(MiniLabMk2, self)._create_session()
        self._session.set_enabled(False)

    @subject_slot("live_mode")
    def _on_live_mode_changed(self, is_live_mode_on):
        self._session.set_enabled(is_live_mode_on)

    def _collect_setup_messages(self):
        super(MiniLabMk2, self)._collect_setup_messages()
        self._messages_to_send.append(SETUP_MSG_PREFIX + (STORE_IN_MEMORY_COMMAND, LIVE_MEMORY_SLOT_ID) + SETUP_MSG_SUFFIX)
        self._messages_to_send.append(SETUP_MSG_PREFIX + (LOAD_MEMORY_COMMAND, ANALOG_LAB_MEMORY_SLOT_ID) + SETUP_MSG_SUFFIX)

    def _setup_hardware(self):

        def send_subsequence(subseq):
            for msg in subseq:
                self._send_midi(msg)

        sequence_to_run = [Task.run(partial(send_subsequence, subsequence)) for subsequence in split_list(self._messages_to_send, 20)]
        self._tasks.add((Task.sequence)(*sequence_to_run))
        self._messages_to_send = []
