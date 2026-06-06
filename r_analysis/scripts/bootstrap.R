bootstrap_r_analysis <- function() {
  if (!exists("PROJECT_ROOT", inherits = TRUE)) {
    config_path <- file.path(getwd(), "r_analysis", "config", "settings.R")
    if (!file.exists(config_path)) {
      stop(
        "Open sonoda-keiba-program.Rproj or set SONODA_KEIBA_ROOT to the repo root."
      )
    }
    source(config_path, encoding = "UTF-8")
  }
  source(
    file.path(PROJECT_ROOT, "r_analysis", "R", "00_source_all.R"),
    encoding = "UTF-8"
  )
}
