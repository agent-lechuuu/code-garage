#!/usr/bin/env bash
# Code Garage safety tools (root; idempotent; run by infra/install.sh). Docs: docs/safety.md.
#   scanners  /opt/garage/scanners: venv with NVIDIA SkillSpector 2.13.2 + Cisco mcp-scanner 4.8.7 (every package
#             pinned by version and sha256), Aguara 0.28.0 (release tarball, sha256 checked), gitleaks (Ubuntu
#             package, linked), versions.json for the scan records
#   dirs      $GARAGE_HOME/state/{scans,reviews,promote} (garage) and state/review-inbox (garage:claude, setgid):
#             the weekly AI review job (user claude) writes its verdicts there, garage reads them
#   promote   garage-promote.service + .timer (Sunday 09:30, user garage + group askers for lechu-ask):
#             `garage review --ingest`, then `garage promote --propose` (the owner's card). The timer is only
#             enabled with --enable-promote (the coordinator sends the first card by hand)
# Usage: 30-safety.sh [--enable-promote] [section...]   (no sections = all)
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
DIR=/opt/garage/scanners
AGUARA_VERSION=0.28.0
AGUARA_SHA256=f1e40f0ff1acfb0a14afa7b6a15c24fa6d585a5d9feed63896be482b497e98bf
GITLEAKS_VERSION=8.16.0
ENABLE_PROMOTE=0
log() { printf '\n== %s\n' "$*"; }

sec_scanners() {
  log "scanners: $DIR"
  install -d -m 755 "$DIR" "$DIR/bin"
  local req="$DIR/requirements.txt"
  cat >"$req.new" <<'REQ'
aiohappyeyeballs==2.7.1 --hash=sha256:9243213661e29250eb41368e5daa826fc017156c3b8a11440826b2e3ed376472
aiohttp==3.14.5 --hash=sha256:94684b879ac1d71e4238850c99b62dc1b28d9086b156a2555f082010b85a865c
aiosignal==1.4.0 --hash=sha256:053243f8b92b990551949e63930a839ff0cf0b0ebbe0597b0f3fb19e1a0fe82e
annotated-doc==0.0.5 --hash=sha256:117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101
annotated-types==0.8.0 --hash=sha256:f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0
anthropic==2.3.0 --hash=sha256:aa6a3984f9276f307933d42dc6f58b6efc821a5ecafbc8d1bb5993a066767622
anyio==4.15.1 --hash=sha256:6152fdbbf9a77fdec97731721bebf7c4c44f7c29b424b0065826173efc7ed101
attrs==26.1.0 --hash=sha256:c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309
boolean.py==5.0 --hash=sha256:ef28a70bd43115208441b53a045d1549e2f0ec6e3d08a9d142cbc41c1938e8d9
boto3==1.43.120 --hash=sha256:86978245a7b911549a44df3f805ae4ce94a8154f4ebe4a166631b8a6d7af2697
botocore==1.43.120 --hash=sha256:7f54674f26f0d9a500bf44a1f858e88b70b03c82b2aca385ddf51f6e968bfd01
CacheControl==0.14.4 --hash=sha256:b7ac014ff72ee199b5f8af1de29d60239954f223e948196fa3d84adaffc71d2b
certifi==2026.10.23 --hash=sha256:e9b54de76e530bb6cf0ccd036787103acb58fd42ba930ea8bf948ddbaa2f61d1
cffi==2.1.1 --hash=sha256:b0431303acaea1089ad4b3e9ce4e6518193def1118d4073ca848635ee4ea2e96
charset-normalizer==3.5.2 --hash=sha256:34276fd796040bf0993ab33a369aa572e6979c7aab225a88893667ad8eac8f7a
cisco-ai-mcp-scanner==4.8.7 --hash=sha256:55142609f3519b8fd80ec491c1c3bb9e17c2370fb65d6052a07022d4a8906350
click==8.5.0 --hash=sha256:255bc9599cf7748b4b1a446ccc735421bd08a2ae529a8b88597d3de5664ee360
cryptography==50.0.2 --hash=sha256:9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079
cyclonedx-python-lib==11.12.0 --hash=sha256:0e807521a921a5c3cb8ce1153f8a61d29eedfe76a46aac2796b7c6b573391a54
defusedxml==0.7.1 --hash=sha256:a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61
distro==1.9.0 --hash=sha256:7bffd925d65168f85027d8da9af6bddab658135b840670a223589bc0c8ef02b2
docstring_parser==0.18.0 --hash=sha256:b3fcbed555c47d8479be0796ef7e19c2670d428d72e96da63f3a40122860374b
expandvars==1.1.2 --hash=sha256:d1652fe4e61914f5b88ada93aaedb396446f55ae4621de45c8cb9f66e5712526
fastapi==0.162.0 --hash=sha256:3785963de305dd09912426cb81f2d230fce98ab3521cdfe97265c8d14983128c
fastuuid==0.14.0 --hash=sha256:a8a0dfea3972200f72d4c7df02c8ac70bad1bb4c58d7e0ec1e6f341679073a7f
filelock==4.2.4 --hash=sha256:301241438c57936ef93f4243a94f2559022268bfcf9b375a9a72eb0f8db8358e
frozenlist==1.8.0 --hash=sha256:cba69cb73723c3f329622e34bdbf5ce1f80c21c290ff04256cff1cd3c2036ed2
fsspec==2026.9.0 --hash=sha256:8dd6e646e99ea382bd85f97a45e6b526a442d79423a7dc673f1e2756d05fcb5f
h11==0.16.0 --hash=sha256:63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86
hf-xet==1.7.1 --hash=sha256:f26bfd4a6e31b4e37e749a07e8642589406e8537be05eccfd633a92b95e2fb51
httpcore==1.0.9 --hash=sha256:2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55
httpcore2==2.16.0 --hash=sha256:5c4358319f2602d984ad93182c9fee5160f22e9da7babdda870a5e7c4e2dc34f
httpx==0.28.1 --hash=sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad
httpx2==2.16.0 --hash=sha256:fd2c5d7909e8d86fe92d53020c310ca0e4e431b838c207c5754b9bbf0308d49a
huggingface_hub==2.3.0 --hash=sha256:5da369600233568a126eb5578754935b2add9446b42d9e2fc0927d56840ac1a5
idna==3.20 --hash=sha256:ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c
importlib_metadata==8.9.0 --hash=sha256:e0f761b6ea91ced3b0844c14c9d955224d538105921f8e6754c00f6ca79fba7f
Jinja2==3.1.6 --hash=sha256:85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67
jiter==0.18.0 --hash=sha256:a01642d403b8925f2b1e1bb51b4ba49ece8a2bdc9b9560fc8ed0b1f2b35b567a
jmespath==1.1.0 --hash=sha256:a5663118de4908c91729bea0acadca56526eb2698e83de10cd116ae0f4e97c64
jsonpatch==1.38 --hash=sha256:46260c5df952abd4734a098f94512dc00bc38539152ac3ef069ed0475e4f5695
jsonpointer==3.6 --hash=sha256:a45c858f8a9e171f6b3790ed9446c9382782f6c4cb4589176813c5a553f4cfcd
jsonschema==4.26.0 --hash=sha256:d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce
jsonschema-specifications==2025.9.1 --hash=sha256:98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe
langchain-anthropic==1.7.7 --hash=sha256:ad6a82f53bd77f09e83bdb87f41d0b57843a41c995c735a7ab34626c1124ab63
langchain-aws==1.9.1 --hash=sha256:9a86311e0fc9edc1a6cbef534d0c597a62d40c9cc14e09adf2994cbed7748336
langchain-core==1.7.1 --hash=sha256:2d668788945e824832e19bca05788a25dbb864197d63ec48b583057cf8d975fa
langchain-openai==1.7.3 --hash=sha256:0ab77cc4579b87c50823b7ccb5d8af48d6c6ae2084f156dcdc37151fcc0717e6
langchain-protocol==0.0.20 --hash=sha256:3c935e5e46b0f6f9cb52f45ba7cfa53d1b9fa80c82c4a277d47f03e07f7385b1
langgraph==1.2.18 --hash=sha256:f430f28ea7fbc129c3cf7dc31c19c33dc27d93aeebd25c6d64fd5c1bad93d27d
langgraph-checkpoint==4.3.1 --hash=sha256:215a826935c8db4d9676e79fd95943e5b3847d78604390898e1d98581cc594e5
langgraph-prebuilt==1.1.1 --hash=sha256:fae17c22562e501940eb7aa052a15c58a431febbabf33f8ad172e1b44354a7e4
langgraph-sdk==0.4.10 --hash=sha256:306ede340814e79332812e3b5a8bda2587a09657c95e14e5c7af3370e06c22fe
langsmith==0.14.14 --hash=sha256:9265529ed9a592110cc75fa21f088ed34eb5f56ae680f6e9490e7f65e177386c
license-expression==30.4.4 --hash=sha256:421788fdcadb41f049d2dc934ce666626265aeccefddd25e162a26f23bcbf8a4
litellm==1.93.2 --hash=sha256:cacf35cf703b12c54516fc6464a3e08c6dbb1dcfb97239e1f629294fe36a1cba
markdown-it-py==4.2.0 --hash=sha256:9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a
MarkupSafe==3.0.4 --hash=sha256:a8e9f292fcda89b324f2f5c91d13f1424a153e40fc2756f38ee23b15835ff300
mcp==2.3.0 --hash=sha256:dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377
mcp-types==2.3.0 --hash=sha256:968efdbdaedfab06adae40d378a34395f1090c5921d4be3c9cde283aaf76d91d
mdurl==0.1.2 --hash=sha256:84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8
msgpack==1.2.4 --hash=sha256:5d65b791ce4283e02b6267742ad540899155e1b32887b9cbdda47f38f5a076b5
multidict==7.2.1 --hash=sha256:822a7fcd33f6922b650e1b26594f09d53c5d011fe655fea7ded27b2728ce2a1b
numpy==2.5.4 --hash=sha256:d549420b8858885cea8838a727842249218b9c1da24dd517e25c9c7a948310a3
openai==2.54.0 --hash=sha256:89089789197ccdb87f173a03145ed1598d00795220c93e96cf712b1cbf5e5f2b
opentelemetry-api==1.45.1 --hash=sha256:b31553efa588ae44bc306f863c785c5333a9ecc091248c6ee68b4b6c87fdedfb
orjson==3.13.0 --hash=sha256:58a9619d88f8818d9ab6b39d70d203789457ba13c1ed5d274f33ce9ae7e81a36
ormsgpack==1.13.0 --hash=sha256:8e1bc81dc0b5f55105838e1be312e81320338f6e26f0023a9306d45857c073ca
packageurl-python==0.17.6 --hash=sha256:31a85c2717bc41dd818f3c62908685ff9eebcb68588213745b14a6ee9e7df7c9
packaging==26.3 --hash=sha256:d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c
pip-requirements-parser==32.0.1 --hash=sha256:4659bc2a667783e7a15d190f6fccf8b2486685b6dba4c19c3876314769c57526
pip_api==0.0.35 --hash=sha256:66990d0da25378555cbb538db79384bab92d4617c6350dfd7a2126ba2a3a9894
pip_audit==2.10.1 --hash=sha256:99ef3f600a317c1945f1e89e227ef26e1c2d618429b8bd3fa6f4f7c440c4611a
platformdirs==4.14.0 --hash=sha256:1dadfc59a8a5d7565b3d9270ae8fa71c065595352c4277b41c11ee6c222c4b91
propcache==0.5.4 --hash=sha256:cc07876cfb079b6f6f36d21ce75784ad6c2c6b563eeac0ed26c2fa2669b85df9
puremagic==2.2.0 --hash=sha256:c4f7ed7307f056c787199acfda839555921be1df13abba61e8e6db0c787ae1d0
py-serializable==2.1.0 --hash=sha256:b56d5d686b5a03ba4f4db5e769dc32336e142fc3bd4d68a8c25579ebb0a67304
pycparser==3.12 --hash=sha256:a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e
pydantic==2.14.1 --hash=sha256:9195d967ec791692a04438115466764fb8b9a27b31f14a760437694f40d6b454
pydantic_core==2.50.1 --hash=sha256:42b54c2c90ad348b5e3a85e03e715d572c1fde357ef104cdfe3b03b697a404ea
Pygments==2.21.0 --hash=sha256:2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9
PyJWT==2.15.1 --hash=sha256:42d59d631f7768a1028a64c7ff581a9bf7519804daf91fc5b6c56e30eec5e193
pyparsing==3.3.3 --hash=sha256:ece8c00a69cf01b45d0b1dedabb469c90d8caf996d4fda40f147627a122849a4
python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427
python-dotenv==1.2.4 --hash=sha256:42269a8a5b3fd54ffa6f3d84b18abed50064717576b4ecf03dc4a55d8aa04fdc
python-multipart==0.0.32 --hash=sha256:ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23
pywhatwgurl==0.1.1 --hash=sha256:d67072d3f702f899e6e5de074e7fa14b5c9c5c85f616c6016c4eef9c94113d5f
PyYAML==6.0.3 --hash=sha256:c458b6d084f9b935061bc36216e8a69a7e293a2f1e68bf956dcd9e6cbcd143f5
referencing==0.37.0 --hash=sha256:381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231
regex==2026.5.9 --hash=sha256:0de5cf193997384ed2ca6f1cd4f78055b255d93d82d5a8cd6ba0d11c10b167e4
requests==2.34.2 --hash=sha256:2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0
requests-toolbelt==1.0.0 --hash=sha256:cccfdd665f0a24fcf4726e690f65639d272bb0637b9b92dfd91a5568ccf6bd06
rich==15.0.0 --hash=sha256:33bd4ef74232fb73fe9279a257718407f169c09b78a87ad3d296f548e27de0bb
rpds-py==2026.9.1 --hash=sha256:eac2f5dbafd585dfe31f86a23ebf0d3ba480a9d49ebc87947267b5608d4ea0cd
s3transfer==0.19.3 --hash=sha256:24eb7535804306355e31c952a90022bf5b2f9d760f9a11062c7493a217c08553
shellingham==1.5.4 --hash=sha256:7ecfff8f2fd72616f7481040475a65b2bf8af90a56c89140852d1120324e8686
six==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274
sniffio==1.3.1 --hash=sha256:2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2
sortedcontainers==2.4.0 --hash=sha256:a163dcaede0f1c021485e957a39245190e74249897e2ae4b2aa38595db237ee0
sse-starlette==3.6.0 --hash=sha256:e4dfa4d237d2712cb2b4d4918eda9b457cd6b44bbecdc838af75de836565bafd
starlette==1.10.0 --hash=sha256:478c0ab3b4ced6e82719849c118fa406f0278a3499c1a898cd15cd31bdc38ce4
tenacity==9.2.1 --hash=sha256:9e56f17539296baab7beabb08b92f6ee3d7be92d8be72d763360677c2ad6580e
tiktoken==0.14.0 --hash=sha256:e3442bbb2f0c588cec876061e37ae67b455b9df9978b003c8fe30e45f2ef5b42
tokenizers==0.23.3 --hash=sha256:376851d22bcf9d650a5c3090bb83e6cf9e895fbf0595369fa4cd43c1f69b5f87
tomli==2.5.0 --hash=sha256:7ac2027d37c3afbdf4bdd377f2676f6f1d2122a5be1f1137b49dced590b37e75
tomli_w==1.2.0 --hash=sha256:188306098d013b691fcadc011abd66727d3c414c571bb01b1a174ba8c983cf90
tqdm==4.70.1 --hash=sha256:c293e525e6fef9c20e8728fd4612df02a0aa31bb5fe91ecd93e123b1b7bffa73
tree-sitter==0.25.2 --hash=sha256:260586381b23be33b6191a07cea3d44ecbd6c01aa4c6b027a0439145fcbc3358
tree-sitter-c-sharp==0.23.5 --hash=sha256:aa88a780204cd153c4c1ae2d59c654cee1402212fa0d069823d6d34301587438
tree-sitter-go==0.25.0 --hash=sha256:04b3b3cb4aff18e74e28d49b716c6f24cb71ddfdd66768987e26e4d0fa812f74
tree-sitter-java==0.23.5 --hash=sha256:370b204b9500b847f6d0c5ad584045831cee69e9a3e4d878535d39e4a7e4c4f1
tree-sitter-javascript==0.25.0 --hash=sha256:9dc04ba91fc8583344e57c1f1ed5b2c97ecaaf47480011b92fbeab8dda96db75
tree-sitter-kotlin==1.1.0 --hash=sha256:9a92afe24b634cf914c5812af0f5c53184b1c18bdf6ee5505c83afac81f6bf6c
tree-sitter-php==0.25.1 --hash=sha256:3d59f27bc88351f744815e5ff69a40b04b720a94c984fcc804979c71a19afc3e
tree-sitter-python==0.25.0 --hash=sha256:86f118e5eecad616ecdb81d171a36dde9bef5a0b21ed71ea9c3e390813c3baf5
tree-sitter-ruby==0.23.1 --hash=sha256:f7bcd93972b4ca2803856d4fe0fbd04123ff29c4592bbb9f12a27528bd252341
tree-sitter-rust==0.24.2 --hash=sha256:e033c5a93b57c88e0a835880de39fc802909ff69f57aaff6000211c196ea5190
tree-sitter-typescript==0.23.2 --hash=sha256:e96d36b85bcacdeb8ff5c2618d75593ef12ebaf1b4eace3477e2bdb2abb1752c
truststore==0.10.5 --hash=sha256:9aaaedaefaf06d8b206278cf8b5012bc897f485a874503501e12d776df78951c
typer==0.23.2 --hash=sha256:e9c8dc380f82450b3c851a9b9d5a0edf95d1d6456ae70c517d8b06a50c7a9978
typing-inspection==0.4.4 --hash=sha256:65b8397ba37ccbce054456aaccddfc91e6e3083c92824df348d96ca832f3f147
typing_extensions==4.16.0 --hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8
urllib3==2.8.0 --hash=sha256:0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3
uuid_utils==0.19.0 --hash=sha256:b8060530a8fa27f11947489c79bc36e6ebb465b2d714945364dc397283309417
uvicorn==0.54.0 --hash=sha256:505bdb0f318731d45f1f712071fc781a8981f6847a31c902c9f5e652d4f67faf
websockets==17.3 --hash=sha256:8dbb3862aa649de95660b6337d97101977f160b5b354d07b82fe309874d2c8bc
xxhash==4.0.2 --hash=sha256:318e6c3a31d75ccacd1f9b864e3b857d44c9f4bed5e9d5fb5db1dc2fec82f019
yara-python==4.5.4 --hash=sha256:4c682170f3d5cb3a73aa1bd0dc9ab1c0957437b937b7a83ff6d7ffd366415b9c
yarl==1.25.1 --hash=sha256:30eec96e8a91bd588ce897c9543f6d5d8d34b28fbcba28a4dedf20ebeae9fe57
zipp==4.1.2 --hash=sha256:b30cb6cd253122169c47de245ca24a86bac2a5d3802ba15bf7ba6414eb9e144d
zstandard==0.25.0 --hash=sha256:e09bb6252b6476d8d56100e8147b803befa9a12cea144bbe629dd508800d1ad0
skillspector @ https://github.com/NVIDIA/SkillSpector/releases/download/v2.13.2/skillspector-2.13.2-py3-none-any.whl --hash=sha256:82bd8e468229c949cd178edce058fceb95c415fd845ba924f56e7160c8b4b7ea
REQ
  if [[ ! -x $DIR/venv/bin/skillspector ]] || ! cmp -s "$req.new" "$req"; then
    rm -rf "$DIR/venv"
    python3 -m venv "$DIR/venv"
    # --no-deps + --require-hashes: exactly these files, nothing resolved at install time
    "$DIR/venv/bin/pip" install -q --disable-pip-version-check --no-input --require-hashes --no-deps -r "$req.new"
    "$DIR/venv/bin/pip" check -q >/dev/null
    mv "$req.new" "$req"
  else
    rm -f "$req.new"
  fi
  if [[ ! -x $DIR/bin/aguara ]] || [[ $("$DIR/bin/aguara" version 2>/dev/null) != *"$AGUARA_VERSION"* ]]; then
    local tmp; tmp=$(mktemp -d)
    curl -fsSL -m 120 -o "$tmp/a.tgz" \
      "https://github.com/garagon/aguara/releases/download/v$AGUARA_VERSION/aguara_${AGUARA_VERSION}_linux_amd64.tar.gz"
    echo "$AGUARA_SHA256  $tmp/a.tgz" | sha256sum -c --quiet
    tar -xzf "$tmp/a.tgz" -C "$tmp" aguara LICENSE
    install -m 755 "$tmp/aguara" "$DIR/bin/aguara"
    install -m 644 "$tmp/LICENSE" "$DIR/bin/aguara.LICENSE"
    rm -rf "$tmp"
  fi
  dpkg -s gitleaks >/dev/null 2>&1 || apt-get install -y -q gitleaks >/dev/null
  [[ $(dpkg-query -W -f='${Version}' gitleaks) == "$GITLEAKS_VERSION"* ]] || \
    echo "  WARN gitleaks is $(dpkg-query -W -f='${Version}' gitleaks), expected $GITLEAKS_VERSION" >&2
  ln -sfn /usr/bin/gitleaks "$DIR/bin/gitleaks"
  command -v bwrap >/dev/null || apt-get install -y -q bubblewrap >/dev/null
  "$DIR/venv/bin/python" -I - "$DIR" <<'PY'
import importlib.metadata as m, json, re, subprocess, sys
d = sys.argv[1]
v = {"skillspector": m.version("skillspector"), "mcp-scanner": m.version("cisco-ai-mcp-scanner")}
out = subprocess.run([f"{d}/bin/aguara", "version"], capture_output=True, text=True).stdout
v["aguara"] = re.search(r"\d+\.\d+\.\d+", out).group()
v["gitleaks"] = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "gitleaks"], capture_output=True,
                               text=True).stdout.split("-")[0]
json.dump(v, open(f"{d}/versions.json", "w"), indent=1)
print("  " + ", ".join(f"{k} {x}" for k, x in v.items()))
PY
  chmod -R go-w "$DIR"
}

sec_dirs() {
  log "dirs: $GARAGE_HOME/state (scans, reviews, promote, review-inbox)"
  id garage >/dev/null 2>&1 || { echo "  no user garage: run 10-base.sh first" >&2; exit 1; }
  install -d -m 755 -o garage -g garage "$GARAGE_HOME/state" "$GARAGE_HOME/state/scans" \
    "$GARAGE_HOME/state/reviews" "$GARAGE_HOME/state/promote"
  if getent group claude >/dev/null; then
    install -d -m 2775 -o garage -g claude "$GARAGE_HOME/state/review-inbox"
  else
    install -d -m 755 -o garage -g garage "$GARAGE_HOME/state/review-inbox"
  fi
  install -d -m 755 -o garage -g garage "$GARAGE_HOME/state/review-inbox/done"
  [[ -d $GARAGE_HOME/repo/trust ]] && chown garage:garage "$GARAGE_HOME/repo/trust"
  stat -c '  %A %U:%G %n' "$GARAGE_HOME/state/review-inbox"
}

sec_promote() {
  log "promote: garage-promote.service + timer (Sunday 09:30)"
  getent group askers >/dev/null || groupadd --system askers
  cat >/etc/systemd/system/garage-promote.service <<UNIT
[Unit]
Description=Code Garage: apply the week's AI reviews, then send the owner's promotion card
After=network-online.target lechu-approvals.service

[Service]
Type=oneshot
User=garage
Group=garage
SupplementaryGroups=askers
Environment=GARAGE_HOME=$GARAGE_HOME HOME=/var/lib/garage GIT_TERMINAL_PROMPT=0
ExecStart=-/usr/local/bin/garage review --ingest
ExecStart=/usr/local/bin/garage promote --propose
TimeoutStartSec=45min
Nice=10
IOSchedulingClass=idle
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
# the whole repo + garage's home: trust/registry.yaml is committed and pushed with garage's gh login (garage.trustgit)
ReadWritePaths=$GARAGE_HOME/state $GARAGE_HOME/repo /var/lib/garage
UNIT
  cat >/etc/systemd/system/garage-promote.timer <<'UNIT'
[Unit]
Description=Code Garage weekly promotion card (Sunday 09:30)

[Timer]
OnCalendar=Sun *-*-* 09:30
Persistent=false

[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  if (( ENABLE_PROMOTE )); then
    systemctl enable --now garage-promote.timer >/dev/null 2>&1
  fi
  echo "  garage-promote.timer: $(systemctl is-enabled garage-promote.timer 2>/dev/null || true)"
}

sections=()
for a in "$@"; do
  case $a in
    --enable-promote) ENABLE_PROMOTE=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) sections+=("$a") ;;
  esac
done
(( ${#sections[@]} )) || sections=(scanners dirs promote)
for s in "${sections[@]}"; do "sec_$s"; done
