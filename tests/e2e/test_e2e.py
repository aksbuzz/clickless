import pytest
import time

import httpx
from testcontainers.compose import DockerCompose


@pytest.fixture(scope='module')
def full_app_stack():
  compose = DockerCompose(".")
  with compose as services:
    api_port = services.get_service_port("api", 8000)
    api_base_url = f"http://localhost:{api_port}"

    services.wait_for(api_base_url)

    yield api_base_url

# TEST
@pytest.mark.e2e_tc
def test_full_workflow(full_app_stack):
  api_base_url = full_app_stack

  # Act 
  response = httpx.post(f"{api_base_url}/workflows/invoice_approval/run",
                        json={"data": {"source_invoice_id": "e2e-tc-invoice"}})

  # Assert API response
  assert response.status_code == 200
  instance_id = response.json()["instance_id"]

  # Assert: Poll for completion
  final_instance = poll_for_status(api_base_url, instance_id, "SUCCEEDED")

  assert final_instance is not None


def poll_for_status(base_url, instance_id, expected_status, timeout_seconds=60):
  start_time = time.time()
  while time.time() - start_time < timeout_seconds:
    try:
      response = httpx.get(f"{base_url}/instance/{instance_id}")
      response.raise_for_status()
      if response.json()["status"] == expected_status:
        return response.json()
    except httpx.HTTPError:
      pass

    time.sleep(1)
  
  pytest.fail(f"Timeout: Instance {instance_id} did not reach status {expected_status}.")