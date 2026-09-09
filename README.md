# IC-7300MK2 Remote Control Station - BETA

> [!WARNING]
> This repo is a work in progress and is in a loose alpha/beta stage. Lots of this repo is AI written and under further review before we are considering it publicly available. We're using this public repo to supliment blog posts and research around this topic as quickly as possible.

![7300MK2-Control Software Teaser](/7300control.jpg)

Remote operation of the ICOM IC-7300MK2 over the radio's own network interface:
a Python SDK for the RS-BA1-style UDP protocol, a backend that turns one radio
session into HTTP and WebSocket streams, and a browser front end that runs the
radio - panadapter, receive audio, every control the API exposes.

While there is a lot of exciting software in the works, behind closed doors, I am responsibly releasing this code in waves as I confirm my research on this topic. The screenshot above is fully funtioning in my test environment, but it unfortunately relies on a lot of code that I do not yet understand. As I refactor and grow to understand this codebase more, I will release more of it into the wild. Today, we're starting with the Python SDK that initially started my project.

> [!NOTE]
> **Canonical source:** This repository lives on our self-hosted (not public) Forgejo instance at **`git.turnerservices.cloud`**. Public mirrors on **GitHub**, **GitLab**, and **Codeberg** are **read-only**. We are only going to sync the **main** branch to public repos.

## Project Structure

| Directory | What it is |
|---|---|
| [`ic7300mk2-sdk/`](./ic7300mk2-sdk/) | Python library, no runtime dependencies. One blocking `Radio` per radio: control, spectrum sweeps, receive and transmit audio. |
| [`ai-docs/`](./ai-docs/) | Protocol, architecture and CI-V command documentation. |

## Development

Python tooling is [uv](https://docs.astral.sh/uv/): the repo root is a uv
workspace with one committed `uv.lock`.

```sh
uv sync --all-packages                                        # create .venv with both packages
uv run pytest ic7300mk2-sdk/tests                             # no radio needed
```

`nix develop` gives the same shell (the devcontainer runs it in a container).
On macOS, live runs against the radio need Apple's `/usr/bin/python3`.

## Security note

The radio's login is lightly obfuscated and the radio link has no transport
encryption, so keep the radio on a trusted network segment. Backend session
creation is unauthenticated by design (the radio password is the credential):
put an authenticating proxy or a VPN in front of anything reachable from the
internet. Details in [`ai-docs/ARCHITECTURE.md`](./ai-docs/ARCHITECTURE.md)
sections 6, 11 and 12.

## Credits and sources

Built from live experimentation plus ICOM's public CI-V reference and the
open-source [wfview](https://gitlab.com/eliggett/wfview) and
[kappanhang](https://github.com/nonoo/kappanhang) projects. Full provenance in
[`ai-docs/RESEARCH.md`](./ai-docs/RESEARCH.md).
