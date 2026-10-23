import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parent
APPLICATION_NAME = "ChessBoardOverlay"
BUNDLE_IDENTIFIER = "com.mrhafid.chessboardoverlay"
ENGINE_DIRECTORY = PROJECT_DIRECTORY / "engines"
DIST_DIRECTORY = PROJECT_DIRECTORY / "dist"
WORK_DIRECTORY = PROJECT_DIRECTORY / "build"
NAUTILUS_IMAGES_DIRECTORY = PROJECT_DIRECTORY.parent / "NautilusChess" / "images"
ENGINE_FILE_NAME = "stockfish.exe" if sys.platform == "win32" else "stockfish"
STOCKFISH_RELEASE_URL = "https://github.com/official-stockfish/Stockfish/releases/latest/download/"
STOCKFISH_LICENSE_FILE_NAMES = {"Copying.txt", "COPYING", "COPYING.txt", "AUTHORS"}
PLATFORM_LABELS = {"darwin": "macos", "win32": "windows", "linux": "linux"}


def stockfish_asset_name() -> str:
    if sys.platform == "win32":
        return "stockfish-windows-x86-64-avx2.zip"
    if sys.platform == "darwin":
        return "stockfish-macos-m1-apple-silicon.tar" if platform.machine() == "arm64" else "stockfish-macos-x86-64-avx2.tar"
    return "stockfish-ubuntu-x86-64-avx2.tar"


def make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def extract_archive(archive_path: Path, destination: Path) -> None:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
        return
    with tarfile.open(archive_path) as archive:
        archive.extractall(destination, filter="data")


def download_stockfish() -> None:
    asset_name = stockfish_asset_name()
    with tempfile.TemporaryDirectory() as temporary_directory:
        archive_path = Path(temporary_directory) / asset_name
        extract_directory = Path(temporary_directory) / "extracted"
        print(f"Mengunduh {asset_name}")
        urllib.request.urlretrieve(STOCKFISH_RELEASE_URL + asset_name, archive_path)
        extract_archive(archive_path, extract_directory)
        executable = next(
            path
            for path in extract_directory.rglob("stockfish-*")
            if path.is_file() and path.suffix in ("", ".exe")
        )
        ENGINE_DIRECTORY.mkdir(exist_ok=True)
        shutil.copy2(executable, ENGINE_DIRECTORY / ENGINE_FILE_NAME)
        make_executable(ENGINE_DIRECTORY / ENGINE_FILE_NAME)
        for license_file in extract_directory.rglob("*"):
            if license_file.is_file() and license_file.name in STOCKFISH_LICENSE_FILE_NAMES:
                shutil.copy2(license_file, ENGINE_DIRECTORY / f"stockfish-{license_file.name}")


def copy_installed_stockfish() -> bool:
    installed_engine = shutil.which("stockfish")
    if installed_engine is None:
        return False
    ENGINE_DIRECTORY.mkdir(exist_ok=True)
    shutil.copy2(Path(installed_engine).resolve(), ENGINE_DIRECTORY / ENGINE_FILE_NAME)
    make_executable(ENGINE_DIRECTORY / ENGINE_FILE_NAME)
    return True


def prepare_engine(should_download: bool) -> None:
    if (ENGINE_DIRECTORY / ENGINE_FILE_NAME).is_file():
        return
    if should_download:
        download_stockfish()
        return
    if not copy_installed_stockfish():
        print("Stockfish tidak ditemukan. Aplikasi akan dibuild tanpa engine, pakai --download-stockfish untuk menyertakannya")


def data_argument(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def pyinstaller_arguments() -> list[str]:
    arguments = [
        str(PROJECT_DIRECTORY / "main.py"),
        "--name", APPLICATION_NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST_DIRECTORY),
        "--workpath", str(WORK_DIRECTORY),
        "--specpath", str(WORK_DIRECTORY),
        "--add-data", data_argument(PROJECT_DIRECTORY / "LICENSE", "."),
        "--add-data", data_argument(PROJECT_DIRECTORY / "README.md", "."),
    ]
    for pixel_file in sorted(NAUTILUS_IMAGES_DIRECTORY.glob("*/pixel.txt")):
        arguments += ["--add-data", data_argument(pixel_file, f"NautilusChess/images/{pixel_file.parent.name}")]
    if ENGINE_DIRECTORY.is_dir():
        for engine_file in sorted(ENGINE_DIRECTORY.iterdir()):
            option = "--add-binary" if engine_file.name == ENGINE_FILE_NAME else "--add-data"
            arguments += [option, data_argument(engine_file, "engines")]
    if sys.platform == "darwin":
        arguments += ["--osx-bundle-identifier", BUNDLE_IDENTIFIER]
    return arguments


def archive_build() -> Path:
    archive_path = DIST_DIRECTORY / f"{APPLICATION_NAME}-{PLATFORM_LABELS.get(sys.platform, sys.platform)}.zip"
    archive_path.unlink(missing_ok=True)
    if sys.platform == "darwin":
        subprocess.run(
            ["ditto", "-c", "-k", "--keepParent", str(DIST_DIRECTORY / f"{APPLICATION_NAME}.app"), str(archive_path)],
            check=True,
        )
        return archive_path
    shutil.make_archive(str(archive_path.with_suffix("")), "zip", root_dir=DIST_DIRECTORY, base_dir=APPLICATION_NAME)
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Chess Board Overlay untuk OS yang sedang dipakai")
    parser.add_argument("--download-stockfish", action="store_true", help="unduh Stockfish resmi dan sertakan di aplikasi")
    parser.add_argument("--without-engine", action="store_true", help="build tanpa menyertakan Stockfish")
    arguments = parser.parse_args()
    if not arguments.without_engine:
        prepare_engine(arguments.download_stockfish)
    subprocess.run([sys.executable, "-m", "PyInstaller", *pyinstaller_arguments()], check=True)
    print(f"Selesai: {archive_build()}")


if __name__ == "__main__":
    main()
