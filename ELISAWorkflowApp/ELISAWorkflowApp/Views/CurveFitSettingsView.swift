import SwiftUI

struct CurveFitSettingsView: View {
    @ObservedObject var vm: ProcessingViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Curve Fit Settings (4PL)")
                .font(.title2)
                .fontWeight(.bold)

            Text("Adjust the bounds and initial guesses for the 4-parameter logistic fit.\nParameters — Bottom, Top, IC50, Hill — apply in that column order.")
                .font(.subheadline)
                .foregroundColor(.secondary)

            parameterGrid

            HStack {
                Button("Reset to Standard") { vm.resetFitBounds() }
                    .buttonStyle(.bordered)
                Spacer()
                Button("Done") { dismiss() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(minWidth: 520)
    }

    private var columnWidth: CGFloat { 110 }

    private var parameterGrid: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 8) {
                Text("Parameter")
                    .fontWeight(.semibold)
                    .frame(width: 90, alignment: .leading)
                Text("Lower Bound")
                    .fontWeight(.semibold)
                    .frame(width: columnWidth, alignment: .center)
                Text("Initial Guess")
                    .fontWeight(.semibold)
                    .frame(width: columnWidth, alignment: .center)
                Text("Upper Bound")
                    .fontWeight(.semibold)
                    .frame(width: columnWidth, alignment: .center)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            Divider()

            paramRow(name: "Bottom",
                     lower: $vm.fitLowerBottom,
                     p0: $vm.fitP0Bottom,
                     upper: $vm.fitUpperBottom)
            paramRow(name: "Top",
                     lower: $vm.fitLowerTop,
                     p0: $vm.fitP0Top,
                     upper: $vm.fitUpperTop)
            paramRow(name: "IC50",
                     lower: $vm.fitLowerIC50,
                     p0: $vm.fitP0IC50,
                     upper: $vm.fitUpperIC50)
            paramRow(name: "Hill",
                     lower: $vm.fitLowerHill,
                     p0: $vm.fitP0Hill,
                     upper: $vm.fitUpperHill)
        }
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color.secondary.opacity(0.2)))
    }

    private func paramRow(name: String,
                          lower: Binding<Double>,
                          p0: Binding<Double>,
                          upper: Binding<Double>) -> some View {
        HStack(spacing: 8) {
            Text(name)
                .frame(width: 90, alignment: .leading)
            fitField(lower)
            fitField(p0)
            fitField(upper)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func fitField(_ binding: Binding<Double>) -> some View {
        TextField("", value: binding, format: .number)
            .textFieldStyle(.roundedBorder)
            .frame(width: columnWidth)
            .multilineTextAlignment(.trailing)
    }
}
