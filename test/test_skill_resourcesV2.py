import logging
from os import getenv
from os.path import isdir
from typing import Optional, List

import importlib
import unittest
import yaml
from mock import Mock, patch

from ovos_core.intent_services import PadatiousMatcher, IntentService
from ovos_bus_client import Message
from ovos_bus_client.session import Session, SessionManager
from ovos_config.config import update_mycroft_config, Configuration
from ovos_utils.messagebus import FakeBus
from ovos_utils.log import LOG
from ovos_plugin_manager.skills import find_skill_plugins
from ovos_workshop.skill_launcher import SkillLoader
from ovos_workshop.skills.base import BaseSkill
from ovos_workshop.resource_files import SkillResources


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

CAPTURE_INTENT_MESSAGES = [
    "register_vocab",
    "register_intent",
]


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


class TestSkillIntents(unittest.TestCase):
    messages: List[Message]= list()
    last_message: Optional[Message] = None
    valid_intents = dict()
    intents = set()
    vocab = set()
    regex = set()

    valid_intents = dict()
    negative_intents = dict()
    common_query = dict()

    # make the default session use the test pipeline
    session = Session("default", pipeline=PIPELINE)
    SessionManager.default_session = session
    SessionManager.sessions = {"default": session}

    test_skill_id = 'test_skill.test'
    skill = None


    @classmethod
    def setUpClass(cls) -> None:

        def _on_message(msg):
            cls.last_message = msg
            cls.messages.append(msg)

        skill_folder = getenv("TEST_SKILL_PKG_FOLDER")        
        # Ensure all tested languages are loaded
        import ovos_config
        cls.supported_languages = SkillResources.get_available_languages(skill_folder)
        update_mycroft_config({"secondary_langs": cls.supported_languages})
        importlib.reload(ovos_config.config)

        # Start the IntentService
        cls.bus = FakeBus()
        cls.bus.run_forever()
        cls.intent_service = IntentService(cls.bus)

        for msg_type in CAPTURE_INTENT_MESSAGES:
            cls.bus.on(msg_type, _on_message)

        cls.skill = get_skill_object(skill_entrypoint=skill_folder,
                                     bus=cls.bus,
                                     skill_id=cls.test_skill_id)

        skill_resources = cls.skill.resources.get_inventory()

        # Load the test intent file
        yaml_location = getenv("INTENT_TEST_FILE")
        with open(yaml_location) as f:
            valid_intents = yaml.safe_load(f)

        cls.negative_intents = valid_intents.pop('unmatched intents', dict())
        cls.common_query = valid_intents.pop("common query", dict())
        cls.regex = set(skill_resources['regex'])

        cls.valid_intents = valid_intents
        cls.intents = set(valid_intents["en-us"].keys())
    
    @classmethod
    def tearDownClass(cls) -> None:
        cls.skill.shutdown()

    def test_00_init(self):
        for lang in self.valid_intents:
            if hasattr(self.skill, "_native_langs"):
                # ovos-workshop < 0.0.15
                self.assertIn(lang, self.skill._native_langs, lang)
            else:
                self.assertIn(lang, self.skill.native_langs, lang)
            if use_padacioso:
                intent_containers = self.intent_service.padacioso_service.containers
            else:
                intent_containers = self.intent_service.padatious_service.containers
            self.assertIn(lang, intent_containers)
    
    def test_ressources(self):
        """
        test if all resources are present with all languages
        """
        inventory = self.skill.resources.get_inventory()
        self.assertEqual(inventory["languages"], self.supported_languages)
        for lang in self.supported_languages:
            lang_inventory = self.skill.load_lang(lang=lang).get_inventory()
            self.assertEqual(inventory, lang_inventory)

    def test_intent_registration(self):
        """
        Test if all intents are registered
        """
        registered_intents = set(self.skill.intent_service.intent_names)
        registered_vocab = dict()
        registered_regex = dict()
        for msg in self.messages:
            if msg.msg_type == "register_vocab":
                if msg.data.get('regex'):
                    regex = msg.data["regex"].split(
                        '<', 1)[1].split('>', 1)[0].replace(
                        self.test_skill_id.replace('.', '_'), '')
                    registered_regex.setdefault(regex, list())
                    registered_regex[regex].append(msg["data"]["regex"])
                else:
                    voc_filename = msg.data.get("entity_type", "").replace(
                        self.test_skill_id.replace('.', '_'), '').lower()
                    registered_vocab.setdefault(voc_filename, list())
                    registered_vocab[voc_filename].append(
                        msg.data.get("entity_value", ""))
        self.assertEqual(registered_intents, self.intents,
                         registered_intents)
        if self.vocab:
            self.assertEqual(set(registered_vocab.keys()),
                                self.vocab)
        if self.regex:
            self.assertEqual(set(registered_regex.keys()),
                                self.regex, registered_regex)
        for voc in self.vocab:
            # Ensure every vocab file has at least one entry
            self.assertGreater(len(registered_vocab[voc]), 0)
        for rx in self.regex:
            # Ensure every rx file has exactly one entry
            self.assertTrue(all((rx in line for line in
                                    registered_regex[rx])), self.regex)
        # TODO 

    def test_intents(self):
        """
        Test if all intents are correctly recognized by the intent parser
        """
        for lang in self.valid_intents:
            self.assertIsInstance(lang.split('-')[0], str)
            self.assertIsInstance(lang.split('-')[1], str)
            for intent, examples in self.valid_intents[lang].items():
                intent_event = f'{self.test_skill_id}:{intent}'
                self.skill.events.remove(intent_event)
                intent_handler = Mock()
                self.skill.events.add(intent_event, intent_handler)
                for utt in examples:
                    LOG.info(f"Testing utterance '{utt}'")
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
                        LOG.error(f"received:{self.last_message.serialize()}")
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
        original_failure = self.intent_service.send_complete_intent_failure
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
        
        self.intent_service.send_complete_intent_failure = original_failure

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