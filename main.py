import glob
import hashlib
import itertools
import logging
import os.path
from pathlib import Path

import imagesize
import rich_click as click
from PIL import Image
from fpdf import FPDF
from rich.logging import RichHandler

click.rich_click.USE_RICH_MARKUP = True

click.rich_click.MAX_WIDTH = 240
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True

logging.basicConfig(level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True)])
logger = logging.getLogger(__name__)

CACHE_FOLDER = Path(__file__).parent / '.CACHE'
CACHE_FOLDER.mkdir(exist_ok=True)

TARGET_SIZE = 2480, 1748
CONTENT_MAX_WIDTH = 210 - 8
CONTENT_MAX_HEIGHT = (297. / 2) - 4
CONTENT_RATIO = float(CONTENT_MAX_WIDTH) / CONTENT_MAX_HEIGHT


@click.command()
@click.argument('folder', type=click.Path(exists=True))
@click.option('--out', '-o', default='out.pdf', type=click.Path())
def place(folder, out):
    """
    Takes input folder of images and place them into PDF output file.
    """
    logger.info(f'Loading from folder: {folder}.')

    images = tuple(sorted(itertools.chain(
        # TODO: insensitive
        glob.glob1(folder, '*.png'),
        glob.glob1(folder, '*.jpg'),
        glob.glob1(folder, '*.jpeg'),
    )))

    count = len(images)
    logger.info(f'Found {count} images.')

    pdf = FPDF()

    for i, name in enumerate(images):
        image_ext = Path(name).suffix
        name_hash = hashlib.md5(name.encode()).hexdigest()
        cached_path = (CACHE_FOLDER / name_hash).with_suffix(image_ext)
        image_path = os.path.join(folder, name)

        is_top = i % 2 == 0
        if is_top:
            pdf.add_page()
            # A5 dimensions
            pdf.dashed_line(0, 148, 210, 148)
            center = 105, (148 / 2)
        else:
            center = 105, 148 + (148 / 2)

        if not cached_path.exists():
            logger.info(f'Resizing and caching {name}.')
            im = Image.open(image_path)
            if im.width < im.height:
                # all images will be lanscaped
                im = im.rotate(90, expand=True)
            im.thumbnail(TARGET_SIZE, Image.ANTIALIAS)
            im.save(cached_path)

        width, height = imagesize.get(cached_path)
        ratio = float(width) / height

        logger.info(f'{i + 1}/{count} {name=} {width=} {height=} {ratio=}')

        center_x, center_y = center

        # is wider the designated content space?
        is_wider = ratio >= CONTENT_RATIO

        if is_wider:
            x = center_x - CONTENT_MAX_WIDTH / 2
            y = center_y - ((CONTENT_MAX_WIDTH / ratio) / 2)

            pdf.image(
                cached_path.as_posix(),
                w=CONTENT_MAX_WIDTH,
                x=x, y=y,
            )
        else:
            x = center_x - (CONTENT_MAX_HEIGHT * ratio) / 2
            y = center_y - (CONTENT_MAX_HEIGHT / 2)

            pdf.image(
                cached_path.as_posix(),
                h=CONTENT_MAX_HEIGHT,
                x=x, y=y,
            )
    logging.info(f'Exporting to {out}.large')
    pdf.output(f'{out}.large', "F")

    logging.info(f'Minimizing to {out}')
    os.system(f'gs '
              f'-sDEVICE=pdfwrite '
              f'-dCompatibilityLevel=1.4 '
              f'-dPDFSETTINGS=/printer '
              f'-dNOPAUSE -dQUIET -dBATCH '
              f'-sOutputFile={out} {out}.large')


if __name__ == "__main__":
    place()
