program gbm_simulation_dp
    implicit none
    
    ! Define Double Precision for better numerical stability in finance apps
    integer, parameter :: dp = kind(1.d0)
    
    real(dp), allocatable :: prices(:)
    
    ! Parameters defined as variables or read from input (using default values below for simplicity of copy-paste)
    real(dp) :: S0      ! Initial price
    real(dp) :: mu      ! Drift rate (annualized return)
    real(dp) :: sigma   ! Volatility
    real(dp) :: T       ! Total time horizon in years
    
    integer  :: n_steps, i
    real(dp) :: dt, final_price, exponent_term, z1, z2, w
    
    print *, "Geometric Brownian Motion Simulation (Double Precision)"
    print *, "========================================================"
    
    ! Set default values if you prefer not to type them every time, 
    ! or uncomment the read statements below.
    
    S0 = 100.d0
    mu = 0.08d_0      ! 8% expected return
    sigma = 0.25d_0   ! 25% volatility
    T  = 1.0_d0       ! 1 year simulation
    
    ! Time step (dt). Smaller is more accurate but slower. 
    n_steps = int(T * 365.d0)  ! Daily steps roughly for T=1
    dt = float(n_steps)/n_steps

    print *, "Parameters:"
    print *, "Initial Price (S0): ", S0
    print *, "Drift (mu):         ", mu, "(per annum)"
    print *, "Volatility (sigma): ", sigma, "(per sqrt(time))"
    print *, "Time Horizon (T):   ", T, " years"
    
    ! Allocate array to store path. 
    ! Note: In a real app with millions of paths, you might allocate per-path or use fixed arrays.
    allocatable :: S_path(:,:) 
    
    integer :: num_paths
    
    print *, ""
    print *, "Enter number of simulation paths:"
    read *, num_paths

    if (num_paths <= 0) then
        write(*,'(A,I6,A)') 'Invalid path count. Using default ', num_paths, '.'
        num_paths = 100
    end if
    
    ! Allocate memory for the price matrix: paths x time_steps + 1
    allocate(S_path(num_paths, n_steps+1))

    real(dp), parameter :: pi = acos(-1.d_0)

    do i = 1, num_paths
        
        S_path(i, 1) = S0
        
        ! Loop through each time step for this path
        do j = 2, n_steps + 1
            
            ! Box-Muller Transform to generate two independent standard normals Z1 and Z2.
            ! We only need one (Z), but generating both is cheap.
            
            z1 = rand() - 0.5d_0
            z2 = rand() - 0.5d_0
            
            ! Box-Muller formula: sqrt(-2*ln(U)) * cos(2*pi*V)
            w = sqrt(-2.d_0 * log(abs(z1))) * cos(pi * 2.d_0 * z2)
            
            ! GBM Step: S_{t+dt} = S_t * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
            exponent_term = (mu - 0.5d_0 * sigma**2) * dt + sigma * sqrt(dt) * w
            
            ! Calculate new price carefully to avoid overflow/underflow if possible, 
            though standard exp is usually fine for these ranges.
            S_path(i,j) = S_path(i, j-1) * dexp(exponent_term)

        end do
        
    end do
    
    print *, ""
    print *, "Simulation Complete."
    write(*,'(A,I8,A,E13.4,A)') 'Final Price of last path: ', n_steps+1, S_path(num_paths,n_steps+1), ' (Approximation)'

    deallocate(S_path)
    
end program gbm_simulation_dp

subroutine my_rand()
! This subroutine attempts to use a simple LCG if the system rand is not available or robust.
! However, standard Fortran implies intrinsic RAND exists in many environments like Intel/PGI compilers.
! If you are using GCC/gfortran with minimal flags, this might need replacement by an RNG module.
    call random_number(z1) ! Uses internal seed if not set via SYSTEM_CLOCK or similar setup depending on compiler
end subroutine my_rand