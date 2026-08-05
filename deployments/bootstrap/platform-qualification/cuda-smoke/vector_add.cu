#include <cuda_runtime.h>

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

#define CUDA_CHECK(call)                                                     \
    do {                                                                     \
        const cudaError_t error = (call);                                    \
        if (error != cudaSuccess) {                                          \
            std::cerr << "CUDA error: " << cudaGetErrorString(error)         \
                      << " at " << __FILE__ << ":" << __LINE__ << '\n';      \
            std::exit(EXIT_FAILURE);                                         \
        }                                                                    \
    } while (false)

__global__ void vectorAdd(
    const float* a,
    const float* b,
    float* c,
    const std::size_t size
) {
    const std::size_t index =
        static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;

    if (index < size) {
        c[index] = a[index] + b[index];
    }
}

int main() {
    constexpr std::size_t size = 1U << 20U;
    constexpr std::size_t bytes = size * sizeof(float);

    std::vector<float> hostA(size, 1.0F);
    std::vector<float> hostB(size, 2.0F);
    std::vector<float> hostC(size, 0.0F);

    float* deviceA = nullptr;
    float* deviceB = nullptr;
    float* deviceC = nullptr;

    CUDA_CHECK(cudaMalloc(&deviceA, bytes));
    CUDA_CHECK(cudaMalloc(&deviceB, bytes));
    CUDA_CHECK(cudaMalloc(&deviceC, bytes));

    CUDA_CHECK(cudaMemcpy(
        deviceA,
        hostA.data(),
        bytes,
        cudaMemcpyHostToDevice
    ));

    CUDA_CHECK(cudaMemcpy(
        deviceB,
        hostB.data(),
        bytes,
        cudaMemcpyHostToDevice
    ));

    constexpr int threadsPerBlock = 256;
    const int blocks =
        static_cast<int>((size + threadsPerBlock - 1) / threadsPerBlock);

    vectorAdd<<<blocks, threadsPerBlock>>>(
        deviceA,
        deviceB,
        deviceC,
        size
    );

    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    CUDA_CHECK(cudaMemcpy(
        hostC.data(),
        deviceC,
        bytes,
        cudaMemcpyDeviceToHost
    ));

    for (const float value : hostC) {
        if (std::fabs(value - 3.0F) > 1e-5F) {
            std::cerr << "Validation failed\n";
            return EXIT_FAILURE;
        }
    }

    CUDA_CHECK(cudaFree(deviceA));
    CUDA_CHECK(cudaFree(deviceB));
    CUDA_CHECK(cudaFree(deviceC));

    std::cout << "CUDA vector-add smoke test passed\n";
    return EXIT_SUCCESS;
}
