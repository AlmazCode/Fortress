"""Parse the documented handoff commands without opening data or running training."""
import argparse
from pathlib import Path
import shlex

import pytest
import yaml

from ml.cli import main
from ml.train import TrainConfig


ROOT = Path(__file__).resolve().parents[2]


def documented_commands():
    for name in ("TRAINING.md", "CLI.md"):
        in_code = False
        for number, line in enumerate((ROOT / "docs/model" / name).read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("```"):
                in_code = not in_code
            elif in_code and "python -m ml.cli " in line:
                arguments = shlex.split(line.split("python -m ml.cli ", 1)[1], posix=False)
                yield pytest.param(arguments, id=f"{name}:{number}:{arguments[0]}")


class ParsedCommand(BaseException):
    """Stop at the real parser boundary, before any CLI business operation."""


@pytest.mark.parametrize("arguments", list(documented_commands()))
def test_handoff_examples_match_actual_cli_arguments(arguments, monkeypatch):
    parse = argparse.ArgumentParser.parse_args

    def parse_then_stop(parser, *args, **kwargs):
        result = parse(parser, *args, **kwargs)
        # The common entry point first selects a command; the second parser owns
        # its options. Raising BaseException avoids the CLI's failure handlers.
        if set(vars(result)) != {"command"}:
            raise ParsedCommand()
        return result

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", parse_then_stop)
    if arguments == ["--help"]:
        assert main(arguments) == 0
    elif "--help" in arguments:
        with pytest.raises(SystemExit) as caught:
            main(arguments)
        assert caught.value.code == 0
    else:
        with pytest.raises(ParsedCommand):
            main(arguments)


def test_handoff_train_configuration_is_a_supported_cpu_configuration():
    config = yaml.safe_load((ROOT / "ml/config/train.example.yaml").read_text(encoding="utf-8"))
    parsed = TrainConfig(**config)
    assert parsed.device == "cpu" and parsed.cpu_threads == 1
