"""Validates all python scripts for syntax and linting"""
from unittest import TestCase
import os
import os.path
from pylint import lint
from pylint.reporters.text import TextReporter


PYLINT_ARGS = ["--reports=n", "--output-format=colorized", "--rcfile=.pylintrc"]


# inspired by http://stackoverflow.com/questions/2028268/invoking-pylint-programmatically
class WritableObject(object):
    "dummy output stream for pylint"
    def __init__(self):
        self.content = []

    def write(self, line):
        "dummy write"
        self.content.append(line)

    def read(self):
        "dummy read"
        return self.content

    def print_content(self):
        "prints contents"
        print "".join(self.content)

    def get_errors(self):
        "return the error lines only"
        return [line for line in self.content if line[:3] == "E: "]


class DiscoLintTests(TestCase):
    """Validates all tool files for syntax and linting"""
    def test_linting(self):
        """Validates all python scripts for syntax and linting"""
        where = ["./"]
        accept_extensions = ["py"]
        files = [
            os.path.join(dirpath, filename)
            for path in where
            for dirpath, _, filenames in os.walk(path)
            for filename in filenames
            if "boto_env_" not in dirpath  # ignore any auto-generated virtual envs
            if filename.split(".")[-1] in accept_extensions]

        errors = 0
        for filename in files:
            pylint_output = WritableObject()
            lint.Run([filename] + PYLINT_ARGS, reporter=TextReporter(pylint_output), exit=False)
            pylint_output.print_content()
            errors += len(pylint_output.get_errors())

        # print a summary; only appears if we do `nosetests -s`
        print "Linted {0} files".format(len(files))

        self.assertEquals(errors, 0)
