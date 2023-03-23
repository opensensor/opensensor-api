result=$(doctl registry repository list-tags opensensor | grep latest | grep -o sha256:.* | xargs -i kubectl set image deployment/opensensor-api opensensor-api=registry.digitalocean.com/whitewhale/opensensor@{} -n whitewhale)
echo $result
