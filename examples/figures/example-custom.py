"""Example drawing script for a custom figure.

draw(fig) must be a pure function of `fig`: it runs more than once while text
widths are measured. Everything is drawn with the frame's primitives and
palette role names; the generator still draws the frame and runs every check.
"""


def draw(fig):
    frame = fig.frame
    y = 300
    xs = [frame["x"] + 120, frame["x"] + 480, frame["x"] + 840]
    for x, name in zip(xs, ["Draft", "Review", "Ship"]):
        fig.marker(x, y, 28, "focal" if name == "Review" else "structure")
        fig.text(x, y + 52, name, "box_label", anchor="middle", max_width=300)
    fig.connector([(xs[0] + 30, y), (xs[1] - 30, y)], "flow")
    fig.connector([(xs[1] + 30, y), (xs[2] - 30, y)], "flow")
    fig.connector([(xs[2], y + 80), (xs[2], y + 130), (xs[0], y + 130), (xs[0], y + 80)], "signal")
    fig.zone_label(frame["x"], 220, "Sequence")
