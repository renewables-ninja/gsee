import sys


def progress_bar(current_length: int, total: int):
    """
    Draws a progress bar in the terminal depending on:

    Parameters
    ----------
    current_length : int
        Is the length of the shared memory list "prog_mem",
    total : int
        is the total amount oc coordinate tuples to process
    """
    curr = current_length - 1
    width = 75
    fract = curr / total
    progress = int(fract * width)
    left = width - progress
    sys.stdout.write(
        "\r\t[{}{}{}] {}%".format(
            (progress - 2) * "=", 2 * ">", left * " ", round(fract * 100)
        )
    )
    sys.stdout.flush()
