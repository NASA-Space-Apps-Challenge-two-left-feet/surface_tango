"""Shared worktree links work on hosts without directory symlink privileges."""

import os

from scripts.new_worktree import link_shared


def test_links_share_the_cache_and_env(tmp_path):
    cache = tmp_path / "source cache"
    cache.mkdir()
    (cache / "marker").touch()
    env = tmp_path / "source.env"
    env.touch()

    cache_link = tmp_path / "linked cache"
    env_link = tmp_path / "linked.env"
    link_shared(cache, cache_link)
    link_shared(env, env_link)

    assert cache_link.is_dir()
    assert (cache_link / "marker").is_file()
    assert os.path.samefile(cache, cache_link)
    assert env_link.is_file()
    assert os.path.samefile(env, env_link)
