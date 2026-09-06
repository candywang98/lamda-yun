terraform {
  required_version = ">= 1.8.0"
}

locals {
  service_names = toset([
    "web",
    "control-api",
    "temporal-worker",
    "edge-hub",
    "outbox-dispatcher",
  ])
}

resource "terraform_data" "deployment_contract" {
  for_each = local.service_names

  input = {
    name                   = each.key
    private_network_only   = each.key != "web"
    device_network_access  = false
    requires_pinned_image  = true
    otlp_enabled           = true
  }
}

output "deployment_contract" {
  value = { for key, value in terraform_data.deployment_contract : key => value.output }
}
