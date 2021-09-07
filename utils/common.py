def parse_expression(expression, process_variables):
    if expression[:2] == "${":
        target_value = expression[2:].split("}")[0]
        return process_variables[target_value]
    else:
        return expression