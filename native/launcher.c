// vlow.app/Contents/MacOS/vlow — embeds the bundled CPython and runs `-m vlow`.
//
// Why not a shell script or exec into python? TCC (Microphone, Accessibility)
// attributes permissions to the *running process's executable*, so the main
// binary must stay this one for macOS to show "vlow" in Privacy & Security.
// Embedding libpython keeps the process identity while still running Python.
//
// Layout expected (see scripts/build-release.sh):
//   Contents/MacOS/vlow                    this launcher
//   Contents/Resources/python/lib/...      python-build-standalone + site-packages
//
// Launched with no arguments (Finder, LaunchServices, `open`) it runs
// `python -m vlow`. Any explicit arguments are passed straight to the
// interpreter, so `vlow.app/Contents/MacOS/vlow -m vlow test 4` and
// `... -c 'import vlow'` work for debugging.

#include <Python.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    char exe[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0) {
        fputs("vlow: executable path too long\n", stderr);
        return 1;
    }
    char real[PATH_MAX];
    if (realpath(exe, real) == NULL) {
        perror("vlow: realpath");
        return 1;
    }
    char home[PATH_MAX];
    snprintf(home, sizeof home, "%s/../Resources/python", dirname(real));

    PyConfig cfg;
    PyConfig_InitPythonConfig(&cfg);
    cfg.use_environment = 0;      // ignore PYTHONPATH/PYTHONHOME from the user's shell
    cfg.user_site_directory = 0;  // never pick up ~/.local/lib/python3.x
    cfg.safe_path = 1;            // don't put the cwd on sys.path
    cfg.write_bytecode = 0;       // never write into the signed bundle (pyc are precompiled)

    PyStatus st = PyConfig_SetBytesString(&cfg, &cfg.home, home);
    if (PyStatus_Exception(st)) goto fail;
    st = PyConfig_SetBytesString(&cfg, &cfg.program_name, real);
    if (PyStatus_Exception(st)) goto fail;

    // LaunchServices passes no args (older releases passed -psn_…).
    int inject = argc < 2 || strncmp(argv[1], "-psn_", 5) == 0;
    int nargs = inject ? 3 : argc;
    char **args = calloc((size_t)nargs, sizeof *args);
    args[0] = argv[0];
    if (inject) {
        args[1] = "-m";
        args[2] = "vlow";
    } else {
        for (int i = 1; i < argc; i++) args[i] = argv[i];
    }
    st = PyConfig_SetBytesArgv(&cfg, nargs, args);
    if (PyStatus_Exception(st)) goto fail;

    st = Py_InitializeFromConfig(&cfg);
    if (PyStatus_Exception(st)) goto fail;
    PyConfig_Clear(&cfg);
    return Py_RunMain();

fail:
    PyConfig_Clear(&cfg);
    Py_ExitStatusException(st);
}
