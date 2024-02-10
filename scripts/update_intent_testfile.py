from os import getenv
from os.path import isdir, isfile
from dataclasses import dataclass
from pathlib import Path
from functools import reduce
import operator
import random
import re
from typing import List
import yaml

from ovos_utils.log import LOG
from ovos_utils.messagebus import FakeBus
from ovos_utils import flatten_list
from ovos_workshop.skill_launcher import SkillLoader
from ovos_workshop.skills.base import BaseSkill
from ovos_workshop.intents import IntentBuilder


@dataclass
class Intent:
    service: str
    name: str
    filestems: set
    suffix: str = ""

    def __post_init__(self):
        if self.service == "padatious":
            self.suffix = ".intent"
        elif self.service == "adapt":
            self.suffix = ".voc"


def get_skill_object() -> BaseSkill:
    """
    Get an initialized skill object by entrypoint with the requested skill_id.
    @param skill_entrypoint: Skill plugin entrypoint or directory path
    @param bus: FakeBus instance to bind to skill for testing
    @param skill_id: skill_id to initialize skill with
    @param config_patch: Configuration update to apply
    @returns: Initialized skill object
    """

    bus = FakeBus()
    bus.run_forever()

    skill_folder = getenv("TEST_SKILL_PKG_FOLDER")
    if not skill_folder or not isdir(skill_folder):
        raise ValueError("TEST_SKILL_PKG_FOLDER is not set or invalid")

    LOG.info(f"Loading local skill: {skill_folder}")    
    loader = SkillLoader(bus, skill_folder, "unknown")
    if loader.load():
        return loader.instance
    
    return None


def get_intents_from_skillcode(skill) -> List[Intent]:
    intents = []
    for method_name in dir(skill):
        method = getattr(skill, method_name)
        if callable(method) and hasattr(method, 'intents'):
            for intent in method.intents:
                if isinstance(intent, str):
                    # If the intent is a string, it's the intent name
                    stem = Path(intent).stem
                    # string contains the suffix ".intent"
                    intents.append(Intent("padatious", intent, [stem]))
                elif isinstance(intent, IntentBuilder):
                    vocs = list()
                    if intent.at_least_one:
                        vocs.append(intent.at_least_one[0])
                    if intent.requires:
                        vocs.append((intent.requires[0][0],))
                    if intent.optional:
                        vocs.append((intent.optional[0][0],))

                    intents.append(Intent("adapt", intent.name, vocs))
    return intents


def count_permutations(options):
    permutations = []
    for sublist in options:
        choices = set(flatten_list(sublist))
        permutations.append(len(choices))
    return reduce(operator.mul, permutations, 1)


def generate_sentences(options: List[List[List[str]]],
                       max: int,
                       max_random: int = 0) -> List[str]:
    sentences = []    
    while len(sentences) < min(max, count_permutations(options)):
        # we can add an ai sentence generator in the future
        sentence = []
        for sublist in options:
            choice = random.choice(sublist)
            sentence.append(random.choice(choice))
        _sentence = " ".join(sentence)
        if _sentence not in sentences:
            sentences.append(" ".join(sentence))
    return sentences


def update_resources(skill: BaseSkill):

    if skill is None:
        raise ValueError("Skill not found")
    
    intents = set()
    supported_languages =skill.resources.get_inventory().get("languages")

    # we want the intents used in the code
    # (opposed to being present as resource and not being used in the skill)
    skill_intents = get_intents_from_skillcode(skill)

    # Load the test intent file
    yaml_location = getenv("INTENT_TEST_FILE")
    if not yaml_location or not isfile(yaml_location):
        raise ValueError("INTENT_TEST_FILE is not set or invalid")
    
    with open(yaml_location) as f:
        test_yaml = yaml.safe_load(f)

        for intent in skill_intents:
            intents.add(intent.name)

        # update yaml file based on the present intents
        for lang in supported_languages:
            test_yaml.setdefault(lang, dict())
            resources = skill.load_lang(lang=lang)
            for intent in skill_intents:
                test_yaml[lang].setdefault(intent.name, list())
                present_intents = test_yaml[lang][intent.name]
                valid_intents = []
                # prepare adapt intents
                if intent.service == "adapt":
                    options = [
                        [ flatten_list(resources.load_vocabulary_file(voc))
                        for voc in vocs ] for vocs in intent.filestems
                    ]
                    # filter out intents that don't match the options
                    for line in present_intents:
                        if all(any(any(word in line for word in choice) for choice in option) for option in options):
                            valid_intents.append(line)
                    # add possible combinations of options
                    for option in options:
                        if not any(any(any(word in intent for word in choice) for choice in option) for intent in valid_intents):
                            valid_intents.extend(generate_sentences(options, 4))
                # prepare padatious intents
                elif intent.service == "padatious":
                    options = resources.load_intent_file(intent.name)
                    # substitute entities
                    for i, option in enumerate(options):
                        options[i] = re.sub(r'\{.*?\}', "test", option)
                    # filter out intents that don't match the options
                    for line in present_intents:
                        if line in options:
                            valid_intents.append(line)
                    random.shuffle(options)
                    if len(valid_intents) < 5:
                        for option in options:
                            if option not in valid_intents:
                                valid_intents.append(option)

                test_yaml[lang][intent.name] = valid_intents
        
        LOG.info(f"Test yaml: {test_yaml}")
        with open(yaml_location, "w", encoding='utf8') as f:
            yaml.dump(test_yaml, f, allow_unicode=True)
        
        # shutdown skill
        skill.shutdown()


update_resources(get_skill_object())
