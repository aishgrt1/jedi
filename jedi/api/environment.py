import os
import re
import sys
from subprocess import Popen, PIPE
from collections import namedtuple
# When dropping Python 2.7 support we should consider switching to
# `shutil.which`.
from distutils.spawn import find_executable

from jedi.evaluate.project import Project
from jedi.cache import memoize_method
from jedi.evaluate.compiled.subprocess import get_subprocess, \
    EvaluatorSameProcess, EvaluatorSubprocess

import parso

_VersionInfo = namedtuple('VersionInfo', 'major minor micro')

_SUPPORTED_PYTHONS = ['2.7', '3.3', '3.4', '3.5', '3.6']


class InvalidPythonEnvironment(Exception):
    pass


class _BaseEnvironment(object):
    def get_project(self):
        return Project(self.get_sys_path())

    @memoize_method
    def get_grammar(self):
        version_string = '%s.%s' % (self.version_info.major, self.version_info.minor)
        return parso.load_grammar(version=version_string)


class Environment(_BaseEnvironment):
    def __init__(self, path, executable):
        self._base_path = path
        self._executable = executable
        self.version_info = _get_version(self._executable)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self._base_path)

    def get_evaluator_subprocess(self, evaluator):
        return EvaluatorSubprocess(evaluator, self._get_subprocess())

    def _get_subprocess(self):
        return get_subprocess(self._executable)

    @memoize_method
    def get_sys_path(self):
        # It's pretty much impossible to generate the sys path without actually
        # executing Python. The sys path (when starting with -S) itself depends
        # on how the Python version was compiled (ENV variables).
        # If you omit -S when starting Python (normal case), additionally
        # site.py gets executed.
        return self._get_subprocess().get_sys_path()


class InterpreterEnvironment(_BaseEnvironment):
    def __init__(self):
        self.version_info = _VersionInfo(*sys.version_info[:3])

    def get_evaluator_subprocess(self, evaluator):
        return EvaluatorSameProcess(evaluator)

    def get_sys_path(self):
        return sys.path


def get_default_environment():
    return Environment(sys.prefix, sys.executable)


def find_virtualenvs(paths=None):
    if paths is None:
        paths = []

    for path in paths:
        try:
            executable = _get_executable_path(path)
            yield Environment(path, executable)
        except InvalidPythonEnvironment:
            pass


def find_python_environments():
    """
    Ignores virtualenvs and returns the different Python versions.
    """
    current_version = '%s.%s' % (sys.version_info.major, sys.version_info.minor)
    for version_string in _SUPPORTED_PYTHONS:
        if version_string == current_version:
            yield get_default_environment()
        else:
            try:
                yield get_python_environment('python' + version_string)
            except InvalidPythonEnvironment:
                pass


def get_python_environment(python_name):
    exe = find_executable(python_name)
    if exe is None:
        raise InvalidPythonEnvironment("This executable doesn't exist.")
    path = os.path.dirname(os.path.dirname(exe))
    return Environment(path, exe)


def create_environment(path):
    """
    Make it possible to create
    """
    return Environment(path, _get_executable_path(path))


def _get_executable_path(path):
    """
    Returns None if it's not actually a virtual env.
    """
    bin_folder = os.path.join(path, 'bin')
    activate = os.path.join(bin_folder, 'activate')
    python = os.path.join(bin_folder, 'python')
    if not all(os.path.exists(p) for p in (activate, python)):
        raise InvalidPythonEnvironment("One of bin/activate and bin/python is missing.")
    return python


def _get_version(executable):
    try:
        process = Popen([executable, '--version'], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            raise InvalidPythonEnvironment()
    except OSError:
        raise InvalidPythonEnvironment()

    # Until Python 3.4 wthe version string is part of stderr, after that
    # stdout.
    output = stdout + stderr
    match = re.match(br'Python (\d+)\.(\d+)\.(\d+)', output)
    if match is None:
        raise InvalidPythonEnvironment()

    return _VersionInfo(*[int(m) for m in match.groups()])
