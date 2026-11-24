#!/usr/bin/env bash
set -euo pipefail

# Prepare Net-SNMP from source for Linux builds (e.g. cibuildwheel).
# Builds a minimal, optimized shared library (libnetsnmp.so) without daemons or CLI apps.

NETSNMP_VERSION="${NETSNMP_VERSION:-5.10.rc1}"
EXPECTED_SHA256="${EXPECTED_SHA256:-009cbda7879b1c75cee01df9f4eab2797df47c6c5f90b70aed3e51dce89d8e76}"
PREFIX="${PREFIX:-/usr/local}"

echo "=== Preparing Net-SNMP ${NETSNMP_VERSION} for Linux ==="

if [[ -x "${PREFIX}/bin/net-snmp-config" ]]; then
    INSTALLED_VER=$("${PREFIX}/bin/net-snmp-config" --version || true)
    INSTALLED_LIBDIR=$("${PREFIX}/bin/net-snmp-config" --libdir 2>/dev/null | sed 's/^-L//' || true)
    if [[ "${INSTALLED_VER}" == *"5.10"* && -n "${INSTALLED_LIBDIR}" && -f "${INSTALLED_LIBDIR}/pkgconfig/netsnmp.pc" ]]; then
        echo "Net-SNMP ${INSTALLED_VER} already installed at ${PREFIX}. Skipping build."
        exit 0
    fi
fi

if command -v dnf >/dev/null 2>&1; then
    dnf install -y openssl-devel perl-ExtUtils-MakeMaker || yum install -y openssl-devel perl-ExtUtils-MakeMaker
elif command -v yum >/dev/null 2>&1; then
    yum install -y openssl-devel perl-ExtUtils-MakeMaker
elif command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y libssl-dev perl
elif command -v apk >/dev/null 2>&1; then
    apk add openssl-dev perl make gcc g++ musl-dev linux-headers
fi

WORK_DIR=$(mktemp -d /tmp/netsnmp-build-XXXXXX)
trap 'rm -rf "${WORK_DIR}"' EXIT

ARCHIVE_PATH="${WORK_DIR}/v${NETSNMP_VERSION}.tar.gz"
DOWNLOAD_URL="https://github.com/net-snmp/net-snmp/archive/refs/tags/v${NETSNMP_VERSION}.tar.gz"

echo "Downloading Net-SNMP from ${DOWNLOAD_URL}..."
curl --proto '=https' --proto-redir '=https' -sSL -o "${ARCHIVE_PATH}" "${DOWNLOAD_URL}"

echo "Verifying SHA256 checksum..."
ACTUAL_SHA256=$(sha256sum "${ARCHIVE_PATH}" | awk '{print $1}')
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
    echo "ERROR: SHA256 mismatch! Expected ${EXPECTED_SHA256}, got ${ACTUAL_SHA256}" >&2
    exit 1
fi

echo "Extracting Net-SNMP archive..."
tar -xzf "${ARCHIVE_PATH}" -C "${WORK_DIR}"
SOURCE_DIR="${WORK_DIR}/net-snmp-${NETSNMP_VERSION}"

cd "${SOURCE_DIR}"

NPROCS=$(nproc 2>/dev/null || echo 2)
DEFAULT_MIBS="IP-MIB:IF-MIB:TCP-MIB:UDP-MIB:SNMPv2-MIB:RFC1213-MIB:NOTIFICATION-LOG-MIB:DISMAN-EVENT-MIB:DISMAN-SCHEDULE-MIB:HOST-RESOURCES-MIB:HOST-RESOURCES-TYPES:UCD-SNMP-MIB:UCD-DEMO-MIB:SNMP-TARGET-MIB:NET-SNMP-AGENT-MIB:NET-SNMP-EXTEND-MIB:SNMP-FRAMEWORK-MIB:SNMP-MPD-MIB:SNMP-USER-BASED-SM-MIB:SNMP-VIEW-BASED-ACM-MIB:SNMP-COMMUNITY-MIB:NET-SNMP-VACM-MIB"
DEFAULT_MIBDIRS="\$HOME/.snmp/mibs:/usr/share/snmp/mibs:/usr/share/snmp/mibs/iana:/usr/share/snmp/mibs/ietf:/usr/local/share/snmp/mibs:/var/lib/snmp/mibs:/var/lib/snmp/mibs/iana:/var/lib/snmp/mibs/ietf:${PREFIX}/share/snmp/mibs"

echo "Configuring Net-SNMP ${NETSNMP_VERSION} with minimal shared-library options..."
./configure \
    --prefix="${PREFIX}" \
    --with-defaults \
    --with-mibs="${DEFAULT_MIBS}" \
    --with-mibdirs="${DEFAULT_MIBDIRS}" \
    --enable-shared \
    --disable-static \
    --disable-agent \
    --disable-applications \
    --disable-manuals \
    --disable-scripts \
    --without-perl-modules \
    --disable-embedded-perl \
    --with-openssl \
    --enable-blumenthal-aes

echo "Compiling Net-SNMP (parallelism: ${NPROCS})..."
make -j"${NPROCS}"

echo "Installing Net-SNMP to ${PREFIX}..."
make install

LIBDIR=$("${PREFIX}/bin/net-snmp-config" --libdir | sed 's/^-L//')
INCLUDEDIR=$("${PREFIX}/bin/net-snmp-config" --includedir | sed 's/^-I//')
EXEC_PREFIX=$("${PREFIX}/bin/net-snmp-config" --exec-prefix)
LIBS=$("${PREFIX}/bin/net-snmp-config" --libs)
CFLAGS=$("${PREFIX}/bin/net-snmp-config" --cflags | sed -e 's/[[:space:]]-Werror=declaration-after-statement//g' -e 's/[[:space:]]-Wstrict-prototypes//g')
VERSION=$("${PREFIX}/bin/net-snmp-config" --version)
mkdir -p "${LIBDIR}/pkgconfig"
cat > "${LIBDIR}/pkgconfig/netsnmp.pc" <<EOF
prefix=${PREFIX}
exec_prefix=${EXEC_PREFIX}
libdir=${LIBDIR}
includedir=${INCLUDEDIR}

Name: netsnmp
Description: A collection of libraries for SNMP applications.
Version: ${VERSION}
Libs: -Wl,-rpath,${LIBDIR} ${LIBS}
Cflags: ${CFLAGS}
EOF

if command -v ldconfig >/dev/null 2>&1; then
    ldconfig "${LIBDIR}" 2>/dev/null || true
fi

echo "=== Net-SNMP ${NETSNMP_VERSION} installation complete ==="
"${PREFIX}/bin/net-snmp-config" --version
