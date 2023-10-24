"""
:mod:`alchemiscale_fah.compute.client` --- client for interacting with Folding@Home resources
=============================================================================================

"""

import os
import requests
from typing import Optional
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes

from .models import (
    ProjectData,
    ASWorkServerData,
    ASProjectData,
    JobAction,
    JobActionEnum,
    JobData,
    JobResults,
    FileData,
)


class FahAdaptiveSamplingClient:
    """Client for interacting with a Folding@Home assignment and work server."""

    def __init__(
        self,
        as_api_url: str,
        ws_api_url: str,
        ws_ip_addr: str,
        certificate_file: os.PathLike = "api-certificate.pem",
        key_file: os.PathLike = "api-private.pem",
        verify: bool = True,
    ):
        self.as_api_url = as_api_url
        self.ws_api_url = ws_api_url
        self.ws_ip_addr = ws_ip_addr

        self.certificate = self.read_certificate(certificate_file)

        if key_file is None:
            self.key = self.create_key()
        else:
            self.key = self.read_key(key_file)

        self.verify = verify

    @staticmethod
    def read_key(key_file):
        with open(key_file, "rb") as f:
            pem = f.read()

        return serialization.load_pem_private_key(pem, None, default_backend())

    @staticmethod
    def read_certificate(certificate_file):
        with open(certificate_file, "rb") as f:
            pem = f.read()

        return x509.load_pem_x509_certificate(pem, default_backend())

    @classmethod
    def create_key():
        return rsa.generate_private_key(
            backend=default_backend(), public_exponent=65537, key_size=4096
        )

    @classmethod
    def write_key(key, key_file):
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        with open(key_file, "wb") as f:
            f.write(pem)

    @classmethod
    def generate_csr(key, csr_file):
        """Generate certificate signing request (CSR) using private key.

        It is necessary to create a CSR and present this to an AS in order to
        receive a valid certificate. The CSR will be written in PEM format.

        """
        cn = x509.NameAttribute(NameOID.COMMON_NAME, "joe@example.com")
        csr = x509.CertificateSigningRequestBuilder()
        csr = csr.subject_name(x509.Name([cn]))
        csr = csr.sign(key, hashes.SHA256())

        with open(csr_file, "wb") as f:
            f.write(csr.public_bytes(serialization.Encoding.PEM))

    def _check_status(self, r):
        if r.status_code != 200:
            raise Exception("Request failed with %d: %s" % (r.status_code, r.text))

    def _get(self, api_url, endpoint, **params):
        url = urljoin(api_url, endpoint)
        r = requests.get(url, cert=self.cert, params=params, verify=self.verify)
        self._check_status(r)
        return r.json()

    def _put(self, api_url, endpoint, **data):
        url = urljoin(api_url, endpoint)
        r = requests.put(url, json=data, cert=self.cert, verify=self.verify)
        self._check_status(r)

    def _delete(self, api_url, endpoint):
        url = urljoin(api_url, endpoint)
        r = requests.delete(url, cert=self.cert, verify=self.verify)
        self._check_status(r)

    def _upload(self, api_url, endpoint, filename):
        url = urljoin(api_url, endpoint)
        with open(filename, "rb") as f:
            r = requests.put(url, data=f, cert=self.cert, verify=self.verify)
            self._check_status(r)

    def _download(self, api_url, endpoint, filename):
        url = urljoin(api_url, endpoint)
        r = requests.get(url, cert=self.cert, verify=self.verify, stream=True)
        self._check_status(r)

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        r.close()

    def as_get_ws(self) -> ASWorkServerData:
        """Get work server attributes from assignment server."""
        return ASWorkServerData(**self._get(self.as_api_url, f"/ws/{self.ws_ip_addr}"))

    def as_set_ws(self, as_workserver_data: ASWorkServerData):
        """Set work server attributes on assignment server."""
        return self._put(
            self.as_api_url, f"/ws/{self.ws_ip_addr}", **as_workserver_data
        )

    def as_get_project(self, project_id) -> ASProjectData:
        """Set project attributes on the assignment server."""
        return ASProjectData(
            **self._get(
                self.as_api_url,
                f"/ws/{self.ws_ip_addr}/projects/{project_id}",
            )
        )

    def as_set_project(self, project_id, weight, constraints):
        """Set project attributes on the assignment server."""

        as_project_data = ASProjectData(weight=weight, constraints=constraints)
        self._put(
            self.as_api_url,
            f"/ws/{self.ws_ip_addr}/projects/{project_id}",
            **as_project_data.dict(),
        )

    def as_reset_project(self, project_id):
        """Set project attributes to default on the assignment server.

        Sets project weight to 0, drops all constraints.

        """
        as_project_data = ASProjectData(weight=0, constraints="")
        self._put(
            self.as_api_url,
            f"/ws/{self.ws_ip_addr}/projects/{project_id}",
            **as_project_data.dict(),
        )

    def list_projects(self) -> dict[str, ProjectData]:
        return self._get(self.ws_api_url, f"/projects")

    def create_project(self, project_id, project_data: ProjectData):
        self._put(self.ws_api_url, f"/projects/{project_id}", **project_data)

    def update_project(self, project_id, project_data: ProjectData):
        self.create_project(project_id, project_data)

    def delete_project(self, project_id):
        self._delete(self.ws_api_url, f"/projects/{project_id}")

    def get_project(self, project_id) -> ProjectData:
        return ProjectData(**self._get(self.ws_api_url, f"/projects/{project_id}"))

    def list_project_files(self, project_id) -> list[FileData]:
        """Get a list of files associated with a project.

        Parameters
        ----------
        project_id
            ID of the project
        src
            File to download.
        dest
            Path to download file to.

        """
        return [FileData(**i) for i in self._get(
            self.ws_api_url,
            f"/projects/{project_id}/files",
        )]

    def create_project_file(self, project_id, src: Path, dest: Path):
        """Upload a file to the PROJECT directory tree.

        Parameters
        ----------
        project_id
            ID of the project
        src
            File to upload.
        dest
            Path relative to PROJECT directory to upload to.

        """
        return [FileData(**i) for i in self._upload(
            self.ws_api_url,
            f"/projects/{project_id}/files/{dest}",
            src
        )]

    def delete_project_file(self, project_id, path):
        """Delete a file from the PROJECT directory tree.

        Parameters
        ----------
        project_id
            ID of the project
        path
            File to delete.

        """
        return [FileData(**i) for i in self._delete(
            self.ws_api_url,
            f"/projects/{project_id}/files/{path}",
        )]

    def get_project_file(self, project_id, src, dest):
        """Download a file from the PROJECT directory tree.

        Parameters
        ----------
        project_id
            ID of the project
        src
            File to download.
        dest
            Path to download file to.

        """
        return [FileData(**i) for i in self._download(
            self.ws_api_url,
            f"/projects/{project_id}/files/{src}",
            dest
        )]

    def get_project_jobs(self, project_id, since: datetime) -> JobResults:
        """Get a list of all active jobs for the project.

        Parameters
        ----------
        project_id
            ID of the project
        since 
            If given, only list jobs that have been updated since this time.

        """
        return JobResults(**self._get(self.ws_api_url,
                                      f"/projects/{project_id}/jobs",
                                      since=since.isoformat()))

    def create_run(
        self,
        project_id,
        core_file: Path,
        system_file: Path,
        state_file: Path,
        integrator_file: Path,
    ) -> int:
        # choose next available run_id from number of runs in project
        project_data = self.get_project(project_id)
        run_id = project_data.runs

        # add files for this run to project directory
        for filepath in [core_file, system_file, state_file, integrator_file]:
            self._upload(
                self.ws_api_url,
                f"/projects/{project_id}/files/RUN{run_id}/{filepath.name}",
                filepath,
            )

        # update project data with new run count
        # NOTE: is this really necessary???
        # does the WS do this on its own?
        # need clarity on what runs,clones,gens counts in project data actually do
        project_data_ = project_data.dict()
        project_data_["runs"] = project_data.runs + 1
        project_data_ = ProjectData(**project_data_)
        self.update_project(project_id, project_data_)

        return run_id

    def create_run_file(self, project_id, run_id, src: Path, dest: Path):
            self._upload(
                self.ws_api_url,
                f"/projects/{project_id}/files/RUN{run_id}/{dest}",
                src,
            )

    def delete_run_file(self, project_id, run_id, path: Path):
            self._delete(
                self.ws_api_url,
                f"/projects/{project_id}/files/RUN{run_id}/{path}",
            )

    def get_run_file(self, project_id, run_id, path: Path):
            self._delete(
                self.ws_api_url,
                f"/projects/{project_id}/files/RUN{run_id}/{path}",
            )

    # provided by @jcoffland; not sure this is current
    # def start_run(self, project_id, run_id, clones=0):
    #    """Start a new run."""
    #    self._put(
    #        self.ws_api_url,
    #        f"/projects/{project_id}/runs/{run_id}/create",
    #        clones=clones,
    #    )

    def create_clone(self, project_id, run_id, clone_id):
        """Start a new CLONE for a given RUN."""

        jobaction = JobAction(action=JobActionEnum.create)

        self._put(
            self.ws_api_url,
            f"/projects/{project_id}/runs/{run_id}/clones/{clone_id}",
            **jobaction.dict(),
        )

    def get_clone(self, project_id, run_id, clone_id) -> JobData:
        """Get state information for the given CLONE."""

        return JobData(
            **self._get(
                self.ws_api_url,
                f"/projects/{project_id}/runs/{run_id}/clones/{clone_id}",
            )
        )

    def list_clone_files(self, project_id, run_id, clone_id) -> list[FileData]:
        return [FileData(**i) for i in self._get(
            self.ws_api_url,
            f"/projects/{project_id}/runs/{run_id}/clones/{clone_id}/files",
        )]


    def list_gen_files(self, project_id, run_id, clone_id, gen_id) -> list[FileData]:
        return [FileData(**i) for i in self._get(
            self.ws_api_url,
            f"/projects/{project_id}/runs/{run_id}/clones/{clone_id}/gens/{gen_id}/files",
        )]

    #def get_xtcs(self, project_id, run_id, clone_id):
    #    data = self._get(
    #        self.ws_api_url,
    #        f"/projects/{project_id}/runs/{run_id}/clones/{clone_id}/files",
    #    )

    #    for info in data:
    #        if info["path"].endswith(".xtc"):
    #            self._download(
    #                self.ws_api_url,
    #                f"/projects/{project_id}/runs/{run_id}/clones/{clone_id}/files/{info['path']}",
    #                info["path"],
    #            )
