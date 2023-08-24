import os


class RegionManager:
    @classmethod
    def get_regions(cls, environment: str, region: str = "") -> list:

        if region and region != "None":
            regions = [region]
        else:
            regions = cls.__get_regions(environment)

        return regions

    @staticmethod
    def __get_regions(environment: str) -> list:

        # Create a list of all regions of the env
        paramsDir = f"./params/{environment}/"
        regions = [name for name in os.listdir(paramsDir) if os.path.isdir(os.path.join(paramsDir, name))]

        return regions
