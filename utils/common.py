def parse_expression(expression, process_variables):
    if expression[:2] == "${":
        target_value = expression[2:].split("}")[0]
        parsed_variable = process_variables
        for target in target_value.split("."):
            try:
                parsed_variable = parsed_variable[target]
            except KeyError:
                return expression 
        return parsed_variable
    else:
        return expression