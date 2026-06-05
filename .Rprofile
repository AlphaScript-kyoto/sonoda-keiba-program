# RStudio project bootstrap (sonoda-keiba-program)
local({
  root <- tryCatch(
    normalizePath(getwd(), winslash = "/", mustWork = TRUE),
    error = function(e) NULL
  )
  if (
    !is.null(root) &&
      dir.exists(file.path(root, "r_analysis")) &&
      dir.exists(file.path(root, "data", "processed"))
  ) {
    Sys.setenv(SONODA_KEIBA_ROOT = root)
  }
})
