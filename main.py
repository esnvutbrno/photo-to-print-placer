import hashlib
import itertools
import logging
import os.path
import sys
from pathlib import Path

import bs4
import imagesize
import requests
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


@click.group()
def main():
    pass


@main.command()
@click.argument('folder', type=click.Path(exists=True))
@click.option('--out', '-o', default='out.pdf', type=click.Path())
def place(folder, out):
    """
    Takes input folder of images and place them into PDF output file.
    """
    logger.info(f'Loading from folder: {folder}.')

    images = tuple(sorted(itertools.chain(
        # TODO: insensitive
        Path(folder).rglob('*.png'),
        Path(folder).rglob('*.jpg'),
        Path(folder).rglob('*.jpeg'),
        Path(folder).rglob('*.JPG'),
    )))

    count = len(images)
    logger.info(f'Found {count} images.')

    pdf = FPDF()

    for i, path in enumerate(images):
        image_ext = path.suffix
        name_hash = hashlib.md5(path.as_posix().encode()).hexdigest()
        cached_path = (CACHE_FOLDER / name_hash).with_suffix(image_ext)

        is_top = i % 2 == 0
        if is_top:
            pdf.add_page()
            # A5 dimensions
            pdf.dashed_line(0, 148, 210, 148)
            # 105 is half from 210, which is width of A4
            # 148 is height of A5
            center = 105, (148 / 2)
        else:
            center = 105, 148 + (148 / 2)

        if not cached_path.exists():
            logger.info(f'Resizing and caching {path}.')
            im = Image.open(path)
            if im.width < im.height:
                # all images will be landscaped
                im = im.rotate(90, expand=True)
            im.thumbnail(TARGET_SIZE, Image.ANTIALIAS)
            im.save(cached_path)

        width, height = imagesize.get(cached_path)
        ratio = float(width) / height

        logger.info(f'{i + 1}/{count} {path=} {width=} {height=} {ratio=}')

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


@main.command()
@click.argument('folder', type=click.Path())
@click.option('--urls-file',
              type=click.File('r'),
              default=sys.stdin)
def download(folder: Path, urls_file):
    """
    Takes list of Google Photos urls from stdin (or --urls-file) and downloads them to specified folder.
    Images are downloaded in resolution to match 300DPI on A5.
    """
    folder = Path(__file__).parent / Path(folder)
    folder.mkdir(exist_ok=True)

    sess = requests.Session()
    with urls_file:
        lines = urls_file.read().splitlines()

    for url in lines:
        logger.info(f'Processing {url}')
        response = sess.get(url=url)
        album_id = url.rpartition('/')[2]
        (folder / album_id).mkdir(exist_ok=True)

        page = bs4.BeautifulSoup(response.content, features="html.parser")

        imgs = page.select('img')
        logger.info(f'Found {len(imgs)} images')
        for i, img in enumerate(imgs):
            src = img.attrs.get('src')
            if not src:
                continue

            if '/a/' in src:
                # probably some page icons
                continue

            # 1748x2480
            photo_id = hashlib.md5(src.encode()).hexdigest()

            full_size_src = src.replace('w108', 'w2480').replace('h72', 'h1748').replace('s72', 's2480')

            if full_size_src == src:
                logger.error(f'Nope: {src}')
                exit()

            photo = sess.get(full_size_src)

            with (folder / album_id / photo_id).with_suffix('.jpg').open('wb') as f:
                f.write(photo.content)

            logger.info(f'{i + 1}. photo saved.')


if __name__ == "__main__":
    main()
