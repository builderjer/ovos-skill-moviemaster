# pylint: disable=missing-docstring
import shutil
from json import dumps
from os import environ, getenv, makedirs
from os.path import join, dirname, isdir
from unittest.mock import Mock
import pytest
from ovos_plugin_manager.skills import find_skill_plugins
from ovos_utils.fakebus import FakeBus

from ovos_skill_moviemaster import MovieMaster

@pytest.fixture(scope="session")
def test_skill(test_skill_id="ovos-skill-moviemaster.builderjer", bus=FakeBus()):
    # Get test skill
    bus.emitter = bus.ee
    bus.run_forever()
    skill_entrypoint = getenv("TEST_SKILL_ENTRYPOINT")
    if not skill_entrypoint:
        skill_entrypoints = list(find_skill_plugins().keys())
        assert test_skill_id in skill_entrypoints
        skill_entrypoint = test_skill_id

    skill = MovieMaster(skill_id=test_skill_id, bus=bus)
    skill.speak = Mock()
    skill.speak_dialog = Mock()
    skill.play_audio = Mock()
    yield skill
    shutil.rmtree(join(dirname(__file__), "skill_fs"), ignore_errors=False)


@pytest.fixture(scope="function")
def reset_skill_mocks(test_skill):
    # Reset mocks before each test
    test_skill.speak.reset_mock()
    test_skill.speak_dialog.reset_mock()
    test_skill.play_audio.reset_mock()


class TestMovieMasterSkill:
    test_fs = join(dirname(__file__), "skill_fs")
    data_dir = join(test_fs, "data")
    conf_dir = join(test_fs, "config")
    environ["XDG_DATA_HOME"] = data_dir
    environ["XDG_CONFIG_HOME"] = conf_dir
    if not isdir(test_fs):
        makedirs(data_dir)
        makedirs(conf_dir)

    with open(join(conf_dir, "mycroft.conf"), "w", encoding="utf-8") as f:
        f.write(dumps({"Audio": {"backends": {"ocp": {"active": False}}}}))

    def test_nada(self, test_skill):
        assert True

def test_skill_is_a_valid_plugin():
    assert "ovos-skill-moviemaster.builderjer" in find_skill_plugins()

if __name__ == "__main__":
    pytest.main()
