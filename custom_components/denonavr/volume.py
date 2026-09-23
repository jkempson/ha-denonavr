"""Main-zone volume over telnet in the receiver's 0.5 dB steps."""

from denonavr import DenonAVR

MIN_DB = -80.0
MAX_DB = 18.0


def telnet_volume_command(db: float) -> str:
    """Return the MV command for a volume in dB.

    The receiver counts 00 (-80 dB) to 98 (+18 dB) and takes a half step as a
    third digit, so -30.5 dB is MV495.
    """
    raw = round((min(max(db, MIN_DB), MAX_DB) - MIN_DB) * 2) / 2
    if raw.is_integer():
        return f"MV{int(raw):02d}"
    return f"MV{int(raw * 10):03d}"


async def async_set_volume(receiver: DenonAVR, db: float) -> None:
    """Set the volume, keeping half steps on the main zone's telnet path.

    The library rounds to 0.5 dB and then sends int(volume + 80) over
    telnet, which drops the half step, so the main zone sends its own
    command. Other zones and HTTP-only setups use the library as it is.
    """
    if receiver.telnet_available and receiver.zone == "Main":
        await receiver.async_send_telnet_commands(telnet_volume_command(db))
        return
    await receiver.async_set_volume(db)
