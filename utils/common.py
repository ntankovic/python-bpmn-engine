class SafeDict(dict):
    def __missing__(self, key):
        return "${" + key + "}"


def parse_expression(expression, process_variables):
    key = expression.replace("${", "").replace("}", "")
    if key in process_variables:
        return process_variables[key]
    return expression.replace("${", "{").format_map(SafeDict(process_variables))


if __name__ == "__main__":
    test = "___${a[nice]}___"
    print(parse_expression(test, {"a": {"nice": ["OK"]}}))
