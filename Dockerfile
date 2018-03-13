FROM ubuntu:18.04


ENV WINEPREFIX="/opt/wine64" WINEPATH="c:\\mingw32\\bin"

RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y wine-development dirmngr gnupg2 wget git gettext p7zip-full vim-tiny && \
    ln -sf /usr/lib/wine-development/wine64 /usr/local/bin/wine

ADD ./contrib /contrib
RUN cd /contrib/build-wine && \
    grep -v build-electrum-git.sh build.sh | bash && \
    wine c:/python3.5.4/python.exe -m pip install \
        -r ../deterministic-build/requirements.txt \
        -r ../deterministic-build/requirements-hw.txt

ADD . $WINEPREFIX/drive_c/electrum
RUN cd /contrib/build-wine && ./build-electrum-git.sh
