from enum import Enum, auto


class GenerationHeuristicEnum(Enum):
    """
    This class list the available Heuristics for generating the scenarios
    """
    
    STRICT = 'STRICT' 
    BASIC = 'BASIC' 
    VALIDITY = 'VALIDITY' 

    def casefold(self):
        return self.value.casefold()


# TODO Check this link to use Enum as Choice: https://click.palletsprojects.com/en/stable/parameter-types/ 
if __name__ == "__main__":
    # List the options on the console
    # print(" ".join(list(GenerationHeuristicEnum.__members__)))
    print("BASIC VALIDITY") # for now I ignore STRICT as it doesnt perform well and has few models