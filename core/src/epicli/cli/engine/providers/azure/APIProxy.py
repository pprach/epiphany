import json
import re
import time
from subprocess import Popen, PIPE
from cli.helpers.Log import LogPipe, Log
from cli.helpers.doc_list_helpers import select_first
from cli.helpers.naming_helpers import resource_name
from cli.models.AnsibleHostModel import AnsibleHostModel

class APIProxy:
    def __init__(self, cluster_model, config_docs):
        self.cluster_model = cluster_model
        self.config_docs = config_docs
        self.logger = Log(__name__)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def login(self):
        subscription_name = self.cluster_model.specification.cloud.subscription_name
        all_subscription = self.run(self, 'az login')
        subscription = select_first(all_subscription, lambda x: x['name'] == subscription_name)
        if subscription is None:
            raise Exception(f'User does not have access to subscription: "{subscription_name}"')
        return subscription

    def set_active_subscribtion(self, subscription_id):
        self.run(self, f'az account set --subscription {subscription_id}')  

    def get_active_subscribtion(self):
        subscription = self.run(self, f'az account show') 
        return subscription   
    
    def create_sp(self, app_name, subscription_id):
        #TODO: make role configurable?
        sp = self.run(self, f'az ad sp create-for-rbac -n "{app_name}" --role="Contributor" --scopes="/subscriptions/{subscription_id}"')
        # Sleep for a while. Sometimes the call returns before the rights of the SP are finished creating.
        self.wait(self, 20)
        return sp  

    def get_ips_for_feature(self, component_key):
        look_for_public_ip = self.cluster_model.specification.cloud.use_public_ips
        cluster = f'{self.cluster_model.specification.prefix.lower()}-{self.cluster_model.specification.name.lower()}'      
        running_instances = self.run(self, f'az vm list-ip-addresses --ids $(az resource list --query "[?type==\'Microsoft.Compute/virtualMachines\' && tags.{component_key} == \'\' && tags.cluster == \'{cluster}\'].id" --output tsv)')
        result = []
        for instance in running_instances:
            if isinstance(instance, list):
                instance = instance[0]   
            name = instance['virtualMachine']['name']
            if look_for_public_ip:
                ip = instance['virtualMachine']['network']['publicIpAddresses'][0]['ipAddress']
            else:
                ip = instance['virtualMachine']['network']['privateIpAddresses'][0]
            result.append(AnsibleHostModel(name, ip))
        return result

    @staticmethod
    def wait(self, seconds):        
        for x in range(0, seconds):
            self.logger.info(f'Waiting {seconds} seconds...{x}')
            time.sleep(1)

    @staticmethod
    def run(self, cmd):
        self.logger.info('Running: "' + cmd + '"')

        logpipe = LogPipe(__name__)
        with Popen(cmd, stdout=PIPE, stderr=logpipe, shell=True) as sp:
            logpipe.close()
            try:
                data = sp.stdout.read().decode('utf-8')
                data = re.sub(r'\s+', '', data)
                data = re.sub(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]', '', data)
                output = json.loads(data)
            except:
                output = {}

        if sp.returncode != 0:
            raise Exception(f'Error running: "{cmd}"')
        else:
            self.logger.info(f'Done running "{cmd}"')
            return output            