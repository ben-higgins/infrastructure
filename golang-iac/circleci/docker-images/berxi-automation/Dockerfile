FROM amazonlinux:2 as installer
ARG EXE_URL=https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
ARG EXE_FILENAME=awscliv2.zip

RUN yum update -y \
  && yum install -y unzip curl \
  && curl $EXE_URL -o $EXE_FILENAME \
  && unzip $EXE_FILENAME \
  # The --bin-dir is specified so that we can copy the
  # entire bin directory from the installer stage into
  # into /usr/local/bin of the final stage without
  # accidentally copying over any other executables that
  # may be present in /usr/local/bin of the installer stage.
  && ./aws/install --bin-dir /aws-cli-bin/

FROM amazoncorretto:11.0.8-al2
RUN yum update -y \
  && yum install -y less groff wget tar git openssh \
  && yum clean all \
  && rm -rf /var/cache/yum

# Maven
ARG MAVEN_VERSION=3.6.3
ARG USER_HOME_DIR="/root"
ARG SHA=c35a1803a6e70a126e80b2b3ae33eed961f83ed74d18fcd16909b2d44d7dada3203f1ffe726c17ef8dcca2dcaa9fca676987befeadc9b9f759967a8cb77181c0
ARG BASE_URL=http://apache.mirrors.hoobly.com/maven/maven-3/${MAVEN_VERSION}/binaries

RUN mkdir -p /usr/share/maven /usr/share/maven/ref \
  && echo "Downloading Maven" \
  && wget -O /tmp/apache-maven.tar.gz ${BASE_URL}/apache-maven-${MAVEN_VERSION}-bin.tar.gz \
  && echo "Verifying maven download hash" \
  && echo "${SHA} /tmp/apache-maven.tar.gz" | sha512sum -c - \
  && echo "Installing Maven to /usr/share/maven" \
  && tar -xzf /tmp/apache-maven.tar.gz -C /usr/share/maven --strip-components=1 \
  && echo "Cleaning up and map symlinks" \
  && rm -f /tmp/apache-maven.tar.gz \
  && ln -s /usr/share/maven/bin/mvn /usr/bin/mvn

ENV MAVEN_HOME=/usr/share/maven
ENV MAVEN_CONFIG=/root/.m2

# Copy AWS-CLI from the installer image
COPY --from=installer /usr/local/aws-cli/ /usr/local/aws-cli/
COPY --from=installer /aws-cli-bin/ /usr/local/bin/

# Append AWS Configuration to the image
ADD ./config /data/config
ENV AWS_CONFIG_FILE=/data/config

# Append Custom Scripts to the image
ADD ./scripts /data/scripts

ARG GIT_SHA=AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7PHkccKrpp0yVhp5HdEIcKr6pLlVDBfOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQqZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8xhHTvKSCZIFImWwoG6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3JEAvGq3lGHSZXy28G3skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ==
RUN mkdir /root/.ssh \
  && echo "Configure Github ssh known hosts" \
  && echo "github.com ssh-rsa ${GIT_SHA}" >> /root/.ssh/known_hosts
