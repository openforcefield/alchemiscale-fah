"""Tests for FahAdaptiveSamplingClient.

"""

import pytest

from alchemiscale_fah.compute.client import FahAdaptiveSamplingClient
from alchemiscale_fah.compute.models import ProjectData, JobData, FahProject


class TestFahAdaptiveSamplingClient:

    def test_create_project(self, fah_adaptive_sampling_client):
        client: FahAdaptiveSamplingClient = fah_adaptive_sampling_client

        project_id = 90001

        project_data = ProjectData(
            core_id=0x23,
            contact="lol@no.int",
            atoms=10000,
            credit=5000,
        )

        client.create_project(project_id, project_data)

        project_data_ = client.get_project(project_id)

        assert project_data == project_data_

    def test_create_project_file_from_bytes(self, fah_adaptive_sampling_client):
        client: FahAdaptiveSamplingClient = fah_adaptive_sampling_client

        project_id = 90001

        fah_project = FahProject(
            project_id=project_id, n_atoms=10000, nonbonded_settings="NoCutoff"
        )

        project_file = "alchemiscale-project.txt"

        client.create_project_file_from_bytes(
            project_id, fah_project.json().encode("utf-8"), project_file
        )

        fah_project_ = FahProject.parse_raw(
            client.get_project_file_to_bytes(project_id, project_file).decode("utf-8")
        )

        assert fah_project_ == fah_project

    def test_create_clone(self, fah_adaptive_sampling_client):
        client: FahAdaptiveSamplingClient = fah_adaptive_sampling_client

        project_id = 90001
        run_id = 0
        clone_id = 0

        project_data = ProjectData(
            core_id=0x23,
            contact="lol@no.int",
            atoms=10000,
            credit=5000,
        )

        client.create_project(project_id, project_data)

        client.create_clone(project_id, run_id, clone_id)

        jobdata = client.get_clone(project_id, run_id, clone_id)

        assert jobdata.project == project_id
        assert jobdata.run == run_id
        assert jobdata.clone == clone_id

        assert jobdata.state == "READY"
        assert jobdata.core == 0x23

    def test_get_clone(self, fah_adaptive_sampling_client):
        client: FahAdaptiveSamplingClient = fah_adaptive_sampling_client
        project_id = 90001
        run_id = 0
        clone_id = 0

        project_data = ProjectData(
            core_id=0x23,
            contact="lol@no.int",
            atoms=10000,
            credit=5000,
        )

        client.create_project(project_id, project_data)

        client.create_clone(project_id, run_id, clone_id)

        jobdata = client.get_clone(project_id, run_id, clone_id)

        assert jobdata.project == project_id
        assert jobdata.run == run_id
        assert jobdata.clone == clone_id

        assert jobdata.state == "READY"
        assert jobdata.core == 0x23

        # now, let the job "finish"
        client._finish_clone_mock_ws(project_id, run_id, clone_id)

        jobdata = client.get_clone(project_id, run_id, clone_id)

        assert jobdata.state == "FINISHED"

    def test_create_clone_file(self): ...

    def test_create_clone_file_from_bytes(self): ...

    def test_get_clone_output_file_to_bytes(self): ...