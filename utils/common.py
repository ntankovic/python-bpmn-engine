import functools


class SafeDict(dict):
    def __missing__(self, key):
        return "${" + key + "}"


def parse_expression(expression, process_variables):
    if (key := expression.replace("${", "").replace("}", "")) in process_variables:
        return process_variables[key]

    return expression.replace("${", "{").format_map(SafeDict(process_variables))

def nested_dict_get(dictionary, dotted_key):
    keys = dotted_key.split('.')
    return functools.reduce(lambda d, key: d.get(key) if d else None, keys, dictionary)


if __name__ == "__main__":
    test = "___${a[nice]}___"
    print(parse_expression(test, {"a": {"nice": ["OK"]}}))
