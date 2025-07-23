from .api_fabric import ApiFabric


class ApiFacade:

    def __init__(self):
        self.api_fabric = ApiFabric()

    def get_fabric(self):
        return self.api_fabric
    