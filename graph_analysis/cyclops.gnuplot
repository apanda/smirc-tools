# Note you need gnuplot 4.4 for the pdfcairo terminal.

set terminal pdfcairo font "Gill Sans, 24" linewidth 6 rounded enhanced dashed
  # Line style for axes
set style line 80 lt rgb "#808080"

# Line style for grid
set style line 81 lt 0  # dashed
set style line 81 lt rgb "#808080"  # grey

set grid back linestyle 81
set border 3 back linestyle 80 # Remove border on top and right.  These
# borders are useless and make it harder to see plotted lines near the border.
# Also, put it in grey; no need for so much emphasis on a border.

set xtics nomirror
set ytics nomirror

set ylabel "CDF"
set xlabel "Destination Affected by Individual Link Failure"
set bars small
set output "cyclops.pdf"
set key bottom right
plot "cyclops.cdf" using 1:($2/91442) w linespoints lc -1 lt 1 lw 1 pt 1 title "Destinations affected"


# Note you need gnuplot 4.4 for the pdfcairo terminal.

set terminal pdfcairo font "Gill Sans, 24" linewidth 6 rounded enhanced dashed
  # Line style for axes
set style line 80 lt rgb "#808080"

# Line style for grid
set style line 81 lt 0  # dashed
set style line 81 lt rgb "#808080"  # grey

set grid back linestyle 81
set border 3 back linestyle 80 # Remove border on top and right.  These
# borders are useless and make it harder to see plotted lines near the border.
# Also, put it in grey; no need for so much emphasis on a border.

set xtics nomirror
set ytics nomirror

set ylabel "CDF"
set xlabel "Number of Destinations for which Local Backup Does not Work"
set bars small
set output "cyclops.extreme.pdf"
set key bottom right
plot "cyclops.extreme.cdf" using 1:($2/91442) w linespoints lc -1 lt 1 lw 1 pt 1 title "Destinations affected"
