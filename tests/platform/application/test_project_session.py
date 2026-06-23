"""Tests for ProjectSession — project lifecycle encapsulation."""

from __future__ import annotations

import pytest

from anylabeling.platform.application.project_session import ProjectSession


class TestProjectSessionLifecycle:
    def test_initial_state_not_open(self):
        session = ProjectSession()
        assert not session.is_open
        assert session.project_root is None
        assert session.job_service is None
        assert session.workflow_state is None

    def test_open_project_sets_state(self, tmp_path):
        session = ProjectSession()
        session.open_project(tmp_path)
        assert session.is_open
        assert session.project_root == tmp_path.resolve()
        assert session.job_service is not None
        assert session.workflow_state is not None

    def test_close_project_clears_state(self, tmp_path):
        session = ProjectSession()
        session.open_project(tmp_path)
        session.close_project()
        assert not session.is_open
        assert session.project_root is None
        assert session.job_service is None
        assert session.workflow_state is None

    def test_double_open_closes_first(self, tmp_path):
        session = ProjectSession()
        proj_a = tmp_path / "a"
        proj_a.mkdir()
        proj_b = tmp_path / "b"
        proj_b.mkdir()
        session.open_project(proj_a)
        first_root = session.project_root
        session.open_project(proj_b)
        assert session.project_root == proj_b.resolve()
        assert session.project_root != first_root

    def test_close_when_not_open_is_safe(self):
        session = ProjectSession()
        session.close_project()  # should not raise
        assert not session.is_open

    def test_open_nonexistent_path_raises(self, tmp_path):
        session = ProjectSession()
        bad_path = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            session.open_project(bad_path)

    def test_open_file_instead_of_dir_raises(self, tmp_path):
        session = ProjectSession()
        file_path = tmp_path / "some_file.txt"
        file_path.write_text("hello")
        with pytest.raises(NotADirectoryError):
            session.open_project(file_path)

    def test_refresh_nav_state_no_project(self):
        session = ProjectSession()
        result = session.refresh_navigation_state()
        assert result == {}

    def test_refresh_nav_state_with_project(self, tmp_path):
        session = ProjectSession()
        session.open_project(tmp_path)
        result = session.refresh_navigation_state()
        assert len(result) == 5
        assert result[0].state == "ready"  # PROJECT always ready
