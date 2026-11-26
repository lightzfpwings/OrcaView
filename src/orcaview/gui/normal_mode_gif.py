"""FFmpeg output options for a looping vibration GIF."""


def gif_encoding_args(fps):
    # A per-frame palette lets FFmpeg emit images while frames are still arriving.
    # An ordered dither keeps shading stable on the static parts of the viewport.
    filters = ("split[colors][frames];"
               "[colors]palettegen=stats_mode=single[palette];"
               "[frames][palette]paletteuse=new=1:dither=bayer:bayer_scale=3")
    return ["-filter_complex", filters, "-c:v", "gif", "-loop", "0",
            "-final_delay", str(round(100 / fps)), "-f", "gif"]
