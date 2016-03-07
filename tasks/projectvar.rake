# re-opens the Project module, adding support for fetching a variable from one of
# these sources, in preference order:
#
# 1. Environment variable
# 2. Project variable
# 3. Fallback default value defined here
#
module Project
  DEFAULTS = {
    :IS_TEST_DIR_PEP8 => true,
    :IS_TEST_DIR_PYLINT => false
  }

  ENV_STRING_TO_VALUE = {
    "true" => true,
    "false" => false
  }
  # "true" and "false" in env vars should be coerced to booleans
  def self.string_to_value(value)
    ENV_STRING_TO_VALUE.has_key?(value) ? ENV_STRING_TO_VALUE[value] : value
  end

  def self.[](varname)
    varname_string = varname.to_s
    varname_sym = varname.to_sym

    # Explicit existence checks, rather than using a chain of 'or',
    # so that we correctly handle values that are defined and set to false.
    if ENV.has_key?(varname_string) then
      string_to_value(ENV[varname_string])
    elsif const_defined?(varname) then
      const_get(varname)
    else
      DEFAULTS[varname_sym]
    end
  end
end
