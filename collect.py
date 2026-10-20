#!/usr/bin/env python3
"""Local-only TCP listener discovery and identity-checked termination (Linux)."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import shlex
import signal
import socket
import struct
import sys
import time

PROC = Path('/proc')
MARKERS = ('package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod',
           'Gemfile', 'composer.json', 'mix.exs', 'pom.xml', 'build.gradle')
RUNTIMES = re.compile(r'^(node(js)?|bun|deno|python[\d.]*|pypy[\d.]*|php[\d.]*|ruby[\d.]*|java|go|beam.smp|uvicorn|gunicorn|flask|django-admin|vite|next-server.*|air)$')
# These developer tools expose internal APIs, not project dev servers.
INTERNAL = re.compile(r'(^|[/\s])(opencode|codex|claude|quickshell|omarchy-shell|code|code-insiders|chrome|chromium|firefox|language-server|typescript-language-server|pyright)([/\s]|$)', re.I)


def listeners():
    """Return readable listening sockets in this network namespace, keyed by inode."""
    result = {}
    readable = False
    for name, family in [('tcp', socket.AF_INET), ('tcp6', socket.AF_INET6)]:
        try:
            lines = (PROC / 'net' / name).read_text().splitlines()[1:]
            readable = True
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != '0A':
                continue
            host, port = fields[1].split(':')
            # /proc encodes each 32-bit address word in native byte order.
            raw = b''.join(struct.pack('=I', int(host[i:i + 8], 16))
                           for i in range(0, len(host), 8))
            address = socket.inet_ntop(family, raw)
            result[fields[9]] = {'address': address, 'port': int(port, 16),
                                  'inode': fields[9]}
    if not readable:
        raise OSError('Cannot read /proc/net/tcp or tcp6')
    return result


def identity(pid):
    path = PROC / str(pid)
    if path.stat().st_uid != os.getuid():
        raise PermissionError('Only processes owned by the current user are allowed')
    # comm can contain spaces and parentheses; starttime is field 22.
    fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
    return fields[19]


def socket_inodes(pid):
    result = set()
    for fd in (PROC / str(pid) / 'fd').iterdir():
        try:
            target = os.readlink(fd)
            if target.startswith('socket:['):
                result.add(target[8:-1])
        except OSError:
            pass
    return result


def classify(argv, cwd):
    command = ' '.join(argv)
    if not argv:
        return None
    executable = Path(argv[0]).name
    # Inspect the program, not arbitrary arguments such as --directory /tmp/opencode.
    programs = [executable]
    if executable in ('node', 'nodejs', 'bun', 'deno') and len(argv) > 1 and not argv[1].startswith('-'):
        script = Path(argv[1])
        programs.append(script.stem)
        programs.extend(part for part in script.parts if 'language-server' in part or part == 'pyright')
    if any(INTERNAL.search(program) for program in programs):
        return None
    lower = command.lower()
    for key, label in [('next', 'Next.js'), ('vite', 'Vite'), ('nuxt', 'Nuxt'),
                       ('astro', 'Astro'), ('uvicorn', 'FastAPI / ASGI'),
                       ('gunicorn', 'Gunicorn'), ('flask', 'Flask'),
                       ('manage.py', 'Django'), ('artisan', 'Laravel'),
                       ('rails', 'Rails'), ('http.server', 'Python HTTP')]:
        if key in lower:
            return label
    if RUNTIMES.fullmatch(executable):
        return executable
    # Custom compiled Go/Rust/etc. servers in a project directory.
    if cwd and any((Path(cwd) / marker).is_file() for marker in MARKERS):
        return executable
    return None


def display_command(argv):
    """Shorten invocation paths without changing application arguments."""
    if not argv:
        return ''
    args = list(argv)
    args[0] = Path(args[0]).name
    if args[0] in ('node', 'nodejs', 'bun', 'deno') and len(args) > 1 and not args[1].startswith('-'):
        script = Path(args[1])
        # Framework CLIs are often launched as node /.../dist/.../cli.js.
        framework = re.search(r'(?:^|/)(vite|next|nuxt|astro)(?:/|$)', args[1])
        if framework and (script.suffix in ('.js', '.mjs', '.cjs') or script.name == framework.group(1)):
            args = [framework.group(1)] + args[2:]
        elif args[0] in ('node', 'nodejs') or script.suffix in ('.js', '.mjs', '.cjs', '.ts'):
            args[1] = script.name
    elif re.fullmatch(r'(python[\d.]*|pypy[\d.]*|php[\d.]*|ruby[\d.]*)', args[0]) and len(args) > 1 and not args[1].startswith('-'):
        args[1] = Path(args[1]).name
    return shlex.join(args)


def local_url(address, port, argv):
    ip = ipaddress.ip_address(address)
    if ip.is_unspecified or address in ('127.0.0.1', '::1'):
        # localhost supports both families, including IPv6-only dev servers.
        address = 'localhost'
    host = '[' + address + ']' if ':' in address else address
    scheme = 'https' if '--https' in argv else 'http'
    return f'{scheme}://{host}:{port}'


def snapshot():
    sockets = listeners()
    rows = []
    for path in PROC.iterdir():
        if not path.name.isdecimal():
            continue
        pid = int(path.name)
        try:
            start = identity(pid)
            owned = socket_inodes(pid) & sockets.keys()
            if not owned:
                continue
            argv = [part.decode(errors='replace') for part in
                    (path / 'cmdline').read_bytes().split(b'\0') if part]
            try:
                cwd = os.readlink(path / 'cwd')
            except OSError:
                cwd = ''
            kind = classify(argv, cwd)
            if not kind or identity(pid) != start:
                continue
            for inode in owned:
                item = sockets[inode]
                rows.append(dict(item, pid=pid, startTime=start,
                                 key=f'{pid}:{start}:{inode}', kind=kind,
                                 project=Path(cwd).name if cwd else kind,
                                 cwd=cwd, command=shlex.join(argv),
                                 displayCommand=display_command(argv),
                                 url=local_url(item['address'], item['port'], argv)))
        except (OSError, ValueError, IndexError):
            continue  # Normal process/fd exit races and inaccessible processes.
    rows.sort(key=lambda row: (row['port'], row['pid'], row['address']))
    return {'servers': rows, 'updatedAt': time.time(), 'error': ''}


def stop_process(pid, start, port, inode):
    """Never signal a process group, parent, foreign UID, or recycled PID."""
    if pid <= 1 or pid == os.getpid():
        raise ValueError('Refusing to stop this process')
    # Pin the kernel process identity before checking /proc, including escalation.
    fd = os.pidfd_open(pid)
    try:
        if identity(pid) != start:
            raise ValueError('Process identity changed; refresh and try again')
        live = listeners().get(inode)
        if not live or live['port'] != port or inode not in socket_inodes(pid):
            raise ValueError('This process no longer owns that listening port')
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        poll = select.poll()
        poll.register(fd, select.POLLIN)
        forced = not poll.poll(2500)
        if forced:
            signal.pidfd_send_signal(fd, signal.SIGKILL)
            if not poll.poll(1500):
                raise RuntimeError('Process has not exited yet; check the port again')
        return {'ok': True, 'message': f'Stopped PID {pid}' + (' (forced)' if forced else '')}
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--stop', nargs=4, metavar=('PID', 'START', 'PORT', 'INODE'))
    args = parser.parse_args()
    if args.stop:
        try:
            pid, start, port, inode = args.stop
            result = stop_process(int(pid), start, int(port), inode)
        except (OSError, ValueError, RuntimeError) as error:
            result = {'ok': False, 'message': str(error)}
        print(json.dumps(result), flush=True)
        return
    while True:
        try:
            result = snapshot()
        except OSError as error:
            result = {'servers': [], 'error': str(error), 'updatedAt': time.time()}
        print(json.dumps(result), flush=True)
        if args.once:
            return
        time.sleep(2)


if __name__ == '__main__':
    main()
