# C++ Net-SNMP Porting & Patch Pipeline Standards

This guide documents the patch generation pipeline, C++17 `getopt()` porting invariants, and local macOS Net-SNMP 5.10 development environment setup used in `ezsnmp` and related native C++/SWIG repositories.

---

## 1. Net-SNMP Patch Pipeline (`patches/master_src/`)

> [!CAUTION]
> **Never hand-edit `net-snmp-*-final-patched/*.cpp` or `*.h` directly.**
> Any direct edits to the patched output directory will be overwritten on the next patch regeneration or fail the CI byte-for-byte parity check.

### Source-of-Truth Workflow

1. **Edit Upstream-Derived Sources**: Make all C++ porting changes inside `patches/master_src/` (and patch scripts if adding new files).
2. **Regenerate Patches**: Run `./ezsnmp/patches/do_all_that_stuff.sh 5.10` (or `./patches/make_patches.sh` + `./patches/apply_patches.sh`) to diff `patches/master_src/` against the upstream Net-SNMP tarball sources, emit unified `.patch` files under `ezsnmp/patches/net-snmp-5.10-patches/`, regenerate `net-snmp-*-final-patched/`, and apply `clang-format`.
3. **Byte-for-Byte Parity Invariant**: Verify that re-running the patch pipeline produces zero diff against the committed `net-snmp-*-final-patched/` files (`git diff --exit-code`).

---

## 2. `getopt()` / `optind` / `optreset` C++17 Porting Pitfalls

Upstream Net-SNMP CLI tools (`snmpget`, `snmpwalk`, `snmpbulkwalk`, `snmptrap`, `snmpdf`, `snmpstatus`, `snmptable`, `snmptranslate`, `snmpusm`, etc.) rely on global `getopt()` state and `setjmp`/`longjmp`-style exits that behave unsafely when called repeatedly inside a C++ library:

### 1. Reset `getopt()` Global State Before Every Loop
Because `ezsnmp` invokes argument-parsing routines multiple times within a single process, `getopt()`'s global cursor must be reset before **every** `getopt()` / `snmp_parse_args()` loop:

```cpp
// Cross-platform getopt() state reset before every parsing call:
#if defined(__APPLE__) || defined(__FreeBSD__) || defined(__NetBSD__) || defined(__OpenBSD__)
optind = 1;
optreset = 1;
#else
// GNU/Linux glibc: optind = 0 forces full internal state re-initialization
// (needed when switching argv arrays or re-parsing with optstring changes).
optind = 0;
#endif
```

- **BSD / macOS**: Requires both `optind = 1;` and `optreset = 1;`. Resetting only `optind = 1` leaves internal `place` pointer state stale across calls.
- **GNU / Linux (glibc)**: Does not define `optreset`; setting `optind = 0;` forces glibc's `getopt()` to re-initialize internal state.

### 2. Never Throw C++ Exceptions Inside `getopt()` / `snmp_parse_args()` Callbacks
- `snmp_parse_args()` invokes an `optProc` callback from C linkage (`libnetsnmp`).
- **Never throw a C++ exception directly from inside `optProc` or any `getopt()` callback**—unwinding C++ exceptions across C frames (`libnetsnmp`) causes undefined behavior or `std::terminate()` on macOS/Linux ABI boundaries.
- Instead, **record the error state** (e.g., store the error message/code in a thread-local or context struct) and return an error code from the callback; **throw the C++ exception only after `snmp_parse_args()` returns** to C++.

---

## 3. Generic macOS Net-SNMP 5.10 Development Environment

When building or running native C++ / Python tests locally on macOS against Net-SNMP 5.10:

```bash
# 1. Source the local Net-SNMP 5.10 toolchain environment (CFLAGS, LDFLAGS, PKG_CONFIG_PATH, PATH)
source "$HOME/.local/net-snmp-5.10/env.sh"

# 2. Use the repository's virtual environment Python (from inside your isolated worktree)
<repo>/.venv/bin/python -m pytest python_tests/
```

- Keep all Net-SNMP prefixes referenced via `$HOME/.local/net-snmp-5.10/` (never hardcode user-specific home paths).
- Run builds and test suites inside your dedicated git worktree (`<workspace_root>/wt-<repo>-<task-name>`), never in the primary checkout root.
- **Homebrew-Only on `macos-latest`**: MacPorts (`port install`, `/opt/local`) is removed across CI, `cibuildwheel`, and `prepare_macos_netsnmp.sh`; rely exclusively on Homebrew (`brew`) and `$HOME/.local/net-snmp-5.10/`.

---

## 4. Docker `snmpd` & Valgrind Python 3.12+ Pitfalls

- **Debian 13 `libnl-route-3-dev` Requirement for `snmpd`**: Debian splits `libnl-route-3-dev` from `libnl-3-dev`. Without `libnl-route-3-dev` installed during Net-SNMP source builds, `./configure` detects `netlink/netlink.h` without `rtnl_link_alloc_cache` and silently drops `mibII`, `if-mib`, `ip-mib`, `tcp-mib`, and `udp-mib` from `snmpd` (causing `IF-MIB::ifAdminStatus.1` and interface queries to return `No Such Object`). Always include `libnl-route-3-dev` in Debian Net-SNMP Docker images.
- **Valgrind PEP 489 Multi-Phase Init (`SWIG_mod_exec`)**: On Python 3.12+, SWIG extension module initialization runs inside `SWIG_mod_exec(_object*)` (`PyModule_ExecDef`) rather than `PyInit_*`. Native Valgrind leak checkers must exclude both `PyInit_` and `SWIG_mod_exec` one-time module-load allocations to avoid false positives on Python 3.12+.
