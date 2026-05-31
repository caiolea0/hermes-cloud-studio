"""Minimal SOCKS5 proxy server for Hermes residential tunnel."""
import asyncio
import struct
import socket
import sys

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1080
AUTH_USER = "hermes"
AUTH_PASS = "cuiaba2026"


async def handle_client(reader, writer):
    try:
        # SOCKS5 greeting
        data = await asyncio.wait_for(reader.read(256), timeout=10)
        if len(data) < 3 or data[0] != 0x05:
            writer.close()
            return

        methods = data[2 : 2 + data[1]]
        if 0x02 in methods:
            # Username/password auth
            writer.write(b"\x05\x02")
            await writer.drain()
            auth = await asyncio.wait_for(reader.read(256), timeout=10)
            if len(auth) < 3 or auth[0] != 0x01:
                writer.write(b"\x01\x01")
                await writer.drain()
                writer.close()
                return
            ulen = auth[1]
            username = auth[2 : 2 + ulen].decode()
            plen = auth[2 + ulen]
            password = auth[3 + ulen : 3 + ulen + plen].decode()
            if username == AUTH_USER and password == AUTH_PASS:
                writer.write(b"\x01\x00")
            else:
                writer.write(b"\x01\x01")
                await writer.drain()
                writer.close()
                return
            await writer.drain()
        else:
            # No auth
            writer.write(b"\x05\x00")
            await writer.drain()

        # SOCKS5 request
        data = await asyncio.wait_for(reader.read(256), timeout=10)
        if len(data) < 7 or data[0] != 0x05 or data[1] != 0x01:
            writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await writer.drain()
            writer.close()
            return

        atyp = data[3]
        if atyp == 0x01:  # IPv4
            dst_addr = socket.inet_ntoa(data[4:8])
            dst_port = struct.unpack("!H", data[8:10])[0]
        elif atyp == 0x03:  # Domain
            domain_len = data[4]
            dst_addr = data[5 : 5 + domain_len].decode()
            dst_port = struct.unpack("!H", data[5 + domain_len : 7 + domain_len])[0]
        elif atyp == 0x04:  # IPv6
            dst_addr = socket.inet_ntop(socket.AF_INET6, data[4:20])
            dst_port = struct.unpack("!H", data[20:22])[0]
        else:
            writer.close()
            return

        # Connect to target
        try:
            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(dst_addr, dst_port), timeout=15
            )
        except Exception:
            writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
            await writer.drain()
            writer.close()
            return

        # Success response
        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 4 + struct.pack("!H", dst_port))
        await writer.drain()

        # Relay data
        async def pipe(r, w):
            try:
                while True:
                    chunk = await r.read(8192)
                    if not chunk:
                        break
                    w.write(chunk)
                    await w.drain()
            except Exception:
                pass
            finally:
                try:
                    w.close()
                except Exception:
                    pass

        await asyncio.gather(pipe(reader, remote_writer), pipe(remote_reader, writer))

    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    print(f"SOCKS5 proxy listening on {LISTEN_HOST}:{LISTEN_PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
