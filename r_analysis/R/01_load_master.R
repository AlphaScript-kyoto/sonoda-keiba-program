require_packages <- function() {
  if (!requireNamespace("tidyverse", quietly = TRUE)) {
    stop("Install tidyverse: install.packages('tidyverse')")
  }
}

MASTER_COL_TYPES <- readr::cols(
  race_id = readr::col_character(),
  horse_id = readr::col_character(),
  umaban = readr::col_character(),
  date = readr::col_character(),
  .default = readr::col_guess()
)

load_master_raw <- function() {
  require_packages()
  if (!file.exists(MASTER_CSV)) {
    stop("Missing: ", MASTER_CSV)
  }
  readr::read_csv(
    MASTER_CSV,
    col_types = MASTER_COL_TYPES,
    locale = readr::locale(encoding = "UTF-8"),
    show_col_types = FALSE,
    progress = FALSE
  )
}

filter_analysis_period <- function(df) {
  df <- df |>
    dplyr::mutate(date_chr = as.character(.data$date))
  if (!is.null(ANALYSIS_DATE_FROM) && nzchar(ANALYSIS_DATE_FROM)) {
    df <- dplyr::filter(df, .data$date_chr >= ANALYSIS_DATE_FROM)
  }
  if (!is.null(ANALYSIS_DATE_TO) && nzchar(ANALYSIS_DATE_TO)) {
    df <- dplyr::filter(df, .data$date_chr <= ANALYSIS_DATE_TO)
  }
  dplyr::select(df, -"date_chr")
}

load_master_filtered <- function() {
  df <- load_master_raw()
  df <- filter_analysis_period(df)
  prepare_race_horse_df(df)
}