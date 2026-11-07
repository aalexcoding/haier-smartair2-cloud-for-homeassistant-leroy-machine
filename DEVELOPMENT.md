# Development / publishing

The distributed archive is an **overlay for an actual GitHub fork**, not a replacement for the upstream Git history or license.

1. Click **Fork** on `bwitosze/haier-smartair2-cloud-for-homeassistant`.
2. Clone your new fork and expand the ZIP **into the root of that clone** (overwrite duplicate files). Ensure `LICENSE` is still present.
3. Run `python scripts/configure_fork.py --github-user YOUR_USERNAME`.
4. Run `python -m pytest -q` and `python -m compileall -q custom_components/haier_smartair2`.
5. Commit to a development branch, then open a PR to `main` in your fork.
6. Test on a separate Home Assistant instance with a V3 cloud device, then with two V3 devices, then with a V2 or local unit. Only then create GitHub pre-release `v0.2.0-beta.1`.

If you prefer CLI:

```bash
git clone https://github.com/YOUR_USERNAME/haier-smartair2-cloud-for-homeassistant.git
cd haier-smartair2-cloud-for-homeassistant
# unzip overlay INTO THIS DIRECTORY (do not delete LICENSE or .git)
python scripts/configure_fork.py --github-user YOUR_USERNAME
python -m pytest -q
python -m compileall -q custom_components/haier_smartair2
git checkout -b feature/v3-cloud
git add custom_components hacs.json README.md COMPATIBILITY.md CHANGELOG.md DEVELOPMENT.md scripts tests .github .gitignore
git commit -m 'Add Haier SmartAir2 cloud V3 control and multi-device support'
git push -u origin feature/v3-cloud
```

**Do not publish a personal HA `/config` directory, `config/.storage`, credentials, access tokens, or backup files.** Public CI only tests the pure protocol module; runtime Home Assistant integration tests still need a Home Assistant test environment.
