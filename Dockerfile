FROM debian:jessie

# The add is before the RUN to ensure we get the latest version of packages
# Docker will cache RUN commands, but because the SHA1 of the dir will be
# different it will not cache this layer
ADD . /tmp/ironic-python-agent

# Add 'testing' for qemu-utils
RUN echo 'APT::Default-Release "jessie";' > /etc/apt/apt.conf.d/10default && \
    sed -e 's/jessie/testing/g' /etc/apt/sources.list > /etc/apt/sources.list.d/testing.list

# Install requirements: Python for ironic-python-agent, others for putting an
# image on disk
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends python2.7 python2.7-dev \
        python-pip qemu-utils parted hdparm util-linux genisoimage git gcc \
        bash coreutils tgt && \
    apt-get -y autoremove && \
    apt-get clean

# Install requirements separately, because pip understands a git+https url
# while setuptools doesn't
RUN pip install --upgrade pip
RUN pip install -r /tmp/ironic-python-agent/requirements.txt

# This will succeed because all the dependencies were installed previously
RUN pip install /tmp/ironic-python-agent
RUN rm -rf /tmp/ironic-python-agent
RUN rm -rf /var/lib/apt/lists/*

# Before cleaning mark packages that are required so they are not removed
RUN apt-mark manual python-setuptools
RUN apt-mark manual python-minimal

# Remove no longer needed packages
RUN apt-get -y purge gcc-4.6 gcc python2.7-dev git && \
    apt-get -y autoremove && \
    apt-get clean

CMD [ "/usr/local/bin/ironic-python-agent" ]
