library(shiny)
library(arrow)
library(dplyr)
library(ggplot2)
library(scales)

# data/ sits one level above the r/ project directory
DATA_ROOT <- file.path(dirname(getwd()), "data")

df <- read_parquet(file.path(DATA_ROOT, "electricity/retail-sales/data.parquet")) |>
  filter(!is.na(price), price > 0)

all_states  <- sort(unique(df$stateDescription))
all_sectors <- c("residential", "commercial", "industrial", "all sectors", "transportation", "other")
all_sectors <- intersect(all_sectors, unique(df$sectorName))  # keep only what exists in data

# ── UI ───────────────────────────────────────────────────────────────────────

ui <- fluidPage(
  titlePanel("U.S. Electricity Rates  ·  cents per kWh"),

  sidebarLayout(
    sidebarPanel(
      width = 3,

      selectInput(
        "sector", "Sector",
        choices  = all_sectors,
        selected = "residential"
      ),

      hr(),

      tags$div(
        style = "display:flex; gap:6px; margin-bottom:6px;",
        actionButton("select_all", "All",   class = "btn-sm btn-default"),
        actionButton("clear_all",  "Clear", class = "btn-sm btn-default")
      ),

      # Scrollable state checklist
      tags$div(
        style = "max-height:520px; overflow-y:auto; border:1px solid #ddd;
                 border-radius:4px; padding:6px 10px;",
        checkboxGroupInput(
          "states", label = NULL,
          choices  = all_states,
          selected = all_states   # start with all selected
        )
      )
    ),

    mainPanel(
      width = 9,
      plotOutput("boxplot", height = "700px")
    )
  )
)

# ── Server ───────────────────────────────────────────────────────────────────

server <- function(input, output, session) {

  observeEvent(input$select_all, {
    updateCheckboxGroupInput(session, "states", selected = all_states)
  })

  observeEvent(input$clear_all, {
    updateCheckboxGroupInput(session, "states", selected = character(0))
  })

  filtered <- reactive({
    req(length(input$states) > 0)
    df |>
      filter(sectorName == input$sector,
             stateDescription %in% input$states)
  })

  output$boxplot <- renderPlot({
    data <- filtered()
    req(nrow(data) > 0)

    # Order states by median price (highest at top after coord_flip)
    state_order <- data |>
      group_by(stateDescription) |>
      summarise(med = median(price, na.rm = TRUE), .groups = "drop") |>
      arrange(med) |>
      pull(stateDescription)

    data |>
      mutate(stateDescription = factor(stateDescription, levels = state_order)) |>
      ggplot(aes(x = stateDescription, y = price)) +
      geom_boxplot(
        fill       = "#3a7abf",
        alpha      = 0.65,
        color      = "#1c3f6e",
        outlier.size  = 0.7,
        outlier.alpha = 0.4
      ) +
      coord_flip() +
      scale_y_continuous(labels = label_number(suffix = "¢")) +
      labs(
        title    = paste0("Electricity Price by State  ·  ", tools::toTitleCase(input$sector)),
        subtitle = "Monthly retail rates, 2001 – present  |  Source: EIA",
        x        = NULL,
        y        = "Price (cents per kWh)"
      ) +
      theme_minimal(base_size = 13) +
      theme(
        plot.title    = element_text(face = "bold"),
        plot.subtitle = element_text(color = "grey50", size = 10),
        panel.grid.major.y = element_blank(),
        panel.grid.minor   = element_blank()
      )
  })
}

shinyApp(ui, server)
