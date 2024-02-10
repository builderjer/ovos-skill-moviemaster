import logging
from os import getenv
from os.path import isdir
from typing import Optional

import importlib
import unittest
import yaml
from mock import Mock, patch

from ovos_core.intent_services import PadatiousService, PadatiousMatcher
from ovos_bus_client import Message
from ovos_bus_client.session import Session, SessionManager
from ovos_config.config import update_mycroft_config, Configuration
from ovos_utils.messagebus import FakeBus
from ovos_utils.log import LOG
from ovos_plugin_manager.skills import find_skill_plugins
from ovos_workshop.skill_launcher import SkillLoader
from ovos_workshop.skills.base import BaseSkill


PIPELINE = ["adapt_high", "adapt_medium", "adapt_low"] 
use_padacioso = getenv("INTENT_ENGINE") == "padacioso"
if use_padacioso:
    PIPELINE.extend(["padacioso_high",
                     "padacioso_medium",
                     "padacioso_low"])
else:
    PIPELINE.extend(["padatious_high",
                     "padatious_medium",
                     "padatious_low"])
LOG.level = logging.DEBUG


class MockPadatiousMatcher(PadatiousMatcher):
    include_med = True
    include_low = False

    def __init__(self, *args, **kwargs):
        PadatiousMatcher.__init__(self, *args, **kwargs)
        LOG.debug("Creating test Padatious Matcher")

    def match_medium(self, utterances, lang=None, __=None):
        if not self.include_med:
            LOG.info(f"Skipping medium confidence check for {utterances}")
            return None
        PadatiousMatcher.match_medium(self, utterances, lang=lang)

    def match_low(self, utterances, lang=None, __=None):
        if not self.include_low:
            LOG.info(f"Skipping low confidence check for {utterances}")
            return None
        PadatiousMatcher.match_low(self, utterances, lang=lang)


def get_skill_object(skill_entrypoint: str, bus: FakeBus,
                     skill_id: str, config_patch: Optional[dict] = None) -> BaseSkill:
    """
    Get an initialized skill object by entrypoint with the requested skill_id.
    @param skill_entrypoint: Skill plugin entrypoint or directory path
    @param bus: FakeBus instance to bind to skill for testing
    @param skill_id: skill_id to initialize skill with
    @param config_patch: Configuration update to apply
    @returns: Initialized skill object
    """
    if config_patch:
        user_config = update_mycroft_config(config_patch)
        if user_config not in Configuration.xdg_configs:
            Configuration.xdg_configs.append(user_config)
    if isdir(skill_entrypoint):
        LOG.info(f"Loading local skill: {skill_entrypoint}")
        loader = SkillLoader(bus, skill_entrypoint, skill_id)
        if loader.load():
            return loader.instance
    plugins = find_skill_plugins()
    if skill_entrypoint not in plugins:
        raise ValueError(f"Requested skill not found: {skill_entrypoint}; available skills: {list(plugins.keys())}")
    plugin = plugins[skill_entrypoint]
    skill = plugin(bus=bus, skill_id=skill_id)
    return skill


class TestSkillIntentMatching(unittest.TestCase):
    test_intents = getenv("INTENT_TEST_FILE")
    with open(test_intents) as f:
        valid_intents = yaml.safe_load(f)
    negative_intents = valid_intents.pop('unmatched intents', dict())
    common_query = valid_intents.pop("common query", dict())
    skill_entrypoint = getenv("TEST_SKILL_ENTRYPOINT_NAME")

    # Ensure all tested languages are loaded
    import ovos_config
    update_mycroft_config({"secondary_langs": list(valid_intents.keys())})
    importlib.reload(ovos_config.config)

    # make the default session use the test pipeline
    session = Session("default", pipeline=PIPELINE)
    SessionManager.default_session = session
    SessionManager.sessions = {"default": session}

    # Start the IntentService
    bus = FakeBus()
    from ovos_core.intent_services import IntentService
    intent_service = IntentService(bus)

    # Create the skill to test
    test_skill_id = 'test_skill.test'
    skill = get_skill_object(skill_entrypoint=skill_entrypoint,
                             bus=bus,
                             skill_id=test_skill_id)
    assert skill.config_core["secondary_langs"] == list(valid_intents.keys())

    last_message = None

    @classmethod
    def setUpClass(cls) -> None:
        def _on_message(msg):
            cls.last_message = msg

        cls.bus.on("message", _on_message)

    def test_00_init(self):
        for lang in self.valid_intents:
            if hasattr(self.skill, "_native_langs"):
                # ovos-workshop < 0.0.15
                self.assertIn(lang, self.skill._native_langs, lang)
            else:
                self.assertIn(lang, self.skill.native_langs, lang)
            self.assertIn(lang,
                            self.intent_service.padatious_service.containers)
            # intents = [intent[1]['name'] for intent in
            #            self.skill.intent_service.registered_intents if
            #            intent[1]['lang'] == lang]
            # LOG.info(f"{lang} intents: {intents}")
            # self.assertIsNotNone(intents, f"No intents registered for {lang}")
            # for intent in self.valid_intents[lang]:
            #     # Validate IntentServiceInterface registration
            #     self.assertIn(f"{self.test_skill_id}:{intent}", intents,
            #                   f"Intent not defined for {lang}")

    def test_intents(self):
        for lang in self.valid_intents:
            self.assertIsInstance(lang.split('-')[0], str)
            self.assertIsInstance(lang.split('-')[1], str)
            for intent, examples in self.valid_intents[lang].items():
                intent_event = f'{self.test_skill_id}:{intent}'
                self.skill.events.remove(intent_event)
                intent_handler = Mock()
                self.skill.events.add(intent_event, intent_handler)
                for utt in examples:
                    if isinstance(utt, dict):
                        data = list(utt.values())[0]
                        utt = list(utt.keys())[0]
                    else:
                        data = list()
                    message = Message('test_utterance',
                                        {"utterances": [utt], "lang": lang})
                    self.intent_service.handle_utterance(message)
                    try:
                        intent_handler.assert_called_once()
                    except AssertionError as e:
                        LOG.error(f"sent:{message.serialize()}")
                        LOG.error(f"received:{self.last_message}")
                        raise AssertionError(utt) from e
                    intent_message = intent_handler.call_args[0][0]
                    self.assertIsInstance(intent_message, Message, utt)
                    self.assertEqual(intent_message.msg_type, intent_event, utt)
                    for datum in data:
                        if isinstance(datum, dict):
                            name = list(datum.keys())[0]
                            value = list(datum.values())[0]
                        else:
                            name = datum
                            value = None
                        if name in intent_message.data:
                            # This is an entity
                            voc_id = name
                        else:
                            # We mocked the handler, data is munged
                            voc_id = f'{self.test_skill_id.replace(".", "_")}' \
                                        f'{name}'
                        self.assertIsInstance(intent_message.data.get(voc_id),
                                                str, intent_message.data)
                        if value:
                            self.assertEqual(intent_message.data.get(voc_id),
                                                value, utt)
                    intent_handler.reset_mock()

    @patch("ovos_core.intent_services.padacioso_service.PadaciosoService",
            new=MockPadatiousMatcher)
    def test_negative_intents(self):
        test_config = self.negative_intents.pop('config', None)
        if test_config:
            MockPadatiousMatcher.include_med = test_config.get('include_med',
                                                                True)
            MockPadatiousMatcher.include_low = test_config.get('include_low',
                                                                False)

        intent_failure = Mock()
        self.intent_service.send_complete_intent_failure = intent_failure

        # # Skip any fallback/converse handling
        # self.intent_service.fallback = Mock()
        # self.intent_service.converse = Mock()
        # if not self.common_query:
        #     # Skip common_qa unless explicitly testing a Common QA skill
        #     self.intent_service.common_qa = Mock()

        for lang in self.negative_intents.keys():
            for utt in self.negative_intents[lang]:
                message = Message('test_utterance',
                                    {"utterances": [utt], "lang": lang})
                self.intent_service.handle_utterance(message)
                try:
                    intent_failure.assert_called_once_with(message)
                    intent_failure.reset_mock()
                except AssertionError as e:
                    LOG.error(self.last_message)
                    raise AssertionError(utt) from e

    def test_common_query(self):
        qa_callback = Mock()
        qa_response = Mock()
        self.skill.events.add('question:action', qa_callback)
        self.skill.events.add('question:query.response', qa_response)
        for lang in self.common_query.keys():
            for utt in self.common_query[lang]:
                if isinstance(utt, dict):
                    data = list(utt.values())[0]
                    utt = list(utt.keys())[0]
                else:
                    data = dict()
                message = Message('test_utterance',
                                    {"utterances": [utt], "lang": lang})
                self.intent_service.handle_utterance(message)
                response = qa_response.call_args[0][0]
                callback = qa_response.call_args[0][0]
                self.assertIsInstance(response, Message)
                self.assertTrue(response.data["phrase"] in utt)
                self.assertEqual(response.data["skill_id"], self.skill.skill_id)
                self.assertIn("callback_data", response.data.keys())
                self.assertIsInstance(response.data["conf"], float)
                self.assertIsInstance(response.data["answer"], str)

                self.assertIsInstance(callback, Message)
                self.assertEqual(callback.data['skill_id'], self.skill.skill_id)
                self.assertEqual(callback.data['phrase'],
                                    response.data['phrase'])
                if not data:
                    continue
                if isinstance(data.get('callback'), dict):
                    self.assertEqual(callback.data['callback_data'],
                                        data['callback'])
                elif isinstance(data.get('callback'), list):
                    self.assertEqual(set(callback.data['callback_data'].keys()),
                                        set(data.get('callback')))
                if data.get('min_confidence'):
                    self.assertGreaterEqual(response.data['conf'],
                                            data['min_confidence'])
                if data.get('max_confidence'):
                    self.assertLessEqual(response.data['conf'],
                                            data['max_confidence'])


if __name__ == "__main__":
    unittest.main()