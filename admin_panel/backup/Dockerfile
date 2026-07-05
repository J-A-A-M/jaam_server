FROM alpine:3.21
RUN apk add --no-cache postgresql16-client gzip bash tzdata unzip wget

# rclone
ARG RCLONE_VERSION=v1.68.2
RUN wget -qO /tmp/rclone.zip \
      "https://github.com/rclone/rclone/releases/download/${RCLONE_VERSION}/rclone-${RCLONE_VERSION}-linux-amd64.zip" \
    && unzip /tmp/rclone.zip -d /tmp \
    && mv /tmp/rclone-*/rclone /usr/local/bin/ \
    && rm -rf /tmp/rclone*

COPY entrypoint.sh /entrypoint.sh
COPY backup.sh     /backup.sh
RUN chmod +x /entrypoint.sh /backup.sh

ENTRYPOINT ["/entrypoint.sh"]
