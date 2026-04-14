/**
 * Member form for create/edit operations.
 */
import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Grid,
    FormControlLabel,
    Checkbox,
    MenuItem,
    Alert,
    Paper,
    Chip,
    InputAdornment,
} from '@mui/material';
import { PhotoCamera } from '@mui/icons-material';
import { membersApi, MemberCreate, MemberUpdate } from '@/api/members';
import { membershipsApi } from '@/api/memberships';
import { membershipPlansApi, MembershipPlan } from '@/api/membershipPlans';
import { salesApi } from '@/api/sales';
import { addDays, format } from 'date-fns';

const memberSchema = z.object({
    first_name: z.string().min(1, 'First name is required'),
    last_name: z.string().min(1, 'Last name is required'),
    email: z.string().optional().transform(v => v === '' ? undefined : v).pipe(z.string().email('Invalid email address').optional()),
    phone: z.string().optional(),
    id_number: z.string().optional(),
    date_of_birth: z.string().optional(),
    address: z.string().optional(),
    consent_given: z.boolean(),
    status: z.enum(['active', 'inactive', 'suspended']).optional(),
});

type MemberFormData = z.infer<typeof memberSchema>;

export const MemberForm: React.FC = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const queryClient = useQueryClient();
    const isEdit = !!id;
    const [createdMemberId, setCreatedMemberId] = React.useState<string | null>(null);

    const { data: member } = useQuery({
        queryKey: ['member', id],
        queryFn: () => membersApi.getMember(id!),
        enabled: isEdit,
    });

    const {
        control,
        handleSubmit,
        formState: { errors },
    } = useForm<MemberFormData>({
        resolver: zodResolver(memberSchema),
        defaultValues: member || {
            first_name: '',
            last_name: '',
            email: '',
            phone: '',
            id_number: '',
            consent_given: false,
            status: 'active',
        },
    });

    const createMutation = useMutation({
        mutationFn: (data: MemberCreate) => membersApi.createMember(data),
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setCreatedMemberId(data.id);
        },
        onError: (error: any) => {
            const detail = error?.response?.data?.detail || error?.message || 'Failed to create member';
            alert('Error creating member: ' + detail);
        },
    });

    const updateMutation = useMutation({
        mutationFn: (data: MemberUpdate) => membersApi.updateMember(id!, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            queryClient.invalidateQueries({ queryKey: ['member', id] });
            navigate('/members');
        },
    });

    // The effective member ID for sub-components
    const effectiveMemberId = id || createdMemberId;
    const showSubSections = isEdit || !!createdMemberId;

    const onSubmit = (data: MemberFormData) => {
        if (isEdit) {
            updateMutation.mutate(data);
        } else {
            createMutation.mutate(data as MemberCreate);
        }
    };

    return (
        <Box>
            <Typography variant="h4" gutterBottom>
                {isEdit ? 'Edit Member' : 'Add Member'}
            </Typography>

            {/* Only show form if member hasn't been created yet */}
            {(!createdMemberId && !isEdit) && (
            <Card>
                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)}>
                        <Grid container spacing={3}>
                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="first_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="First Name"
                                            error={!!errors.first_name}
                                            helperText={errors.first_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="last_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Last Name"
                                            error={!!errors.last_name}
                                            helperText={errors.last_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="id_number"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Cedula / ID Number"
                                            placeholder="e.g. 12345678"
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="email"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Email (optional)"
                                            placeholder="email@example.com"
                                            error={!!errors.email}
                                            helperText={errors.email?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="phone"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Phone"
                                            error={!!errors.phone}
                                            helperText={errors.phone?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="date_of_birth"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Date of Birth"
                                            type="date"
                                            InputLabelProps={{ shrink: true }}
                                        />
                                    )}
                                />
                            </Grid>

                            {isEdit && (
                                <Grid item xs={12} sm={6}>
                                    <Controller
                                        name="status"
                                        control={control}
                                        render={({ field }) => (
                                            <TextField {...field} fullWidth select label="Status">
                                                <MenuItem value="active">Active</MenuItem>
                                                <MenuItem value="inactive">Inactive</MenuItem>
                                                <MenuItem value="suspended">Suspended</MenuItem>
                                            </TextField>
                                        )}
                                    />
                                </Grid>
                            )}

                            <Grid item xs={12}>
                                <Controller
                                    name="address"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField {...field} fullWidth label="Address" multiline rows={2} />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Controller
                                    name="consent_given"
                                    control={control}
                                    render={({ field }) => (
                                        <FormControlLabel
                                            control={<Checkbox {...field} checked={field.value} />}
                                            label="Consent given for biometric data collection"
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Box display="flex" gap={2}>
                                    <Button type="submit" variant="contained" size="large">
                                        {isEdit ? 'Update' : 'Create'}
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        size="large"
                                        onClick={() => navigate('/members')}
                                    >
                                        Cancel
                                    </Button>
                                </Box>
                            </Grid>
                        </Grid>
                    </form>
                </CardContent>
            </Card>
            )}

            {/* Success message after creation */}
            {createdMemberId && !isEdit && (
                <Paper sx={{ p: 3, mb: 3, bgcolor: 'success.lighter', borderRadius: 2 }}>
                    <Typography variant="h6" color="success.main">✅ Member created successfully!</Typography>
                    <Typography variant="body2" color="textSecondary">
                        Now you can assign a membership and enroll their face below.
                    </Typography>
                    <Button sx={{ mt: 1 }} onClick={() => navigate('/members')}>Skip - Go to Members List</Button>
                </Paper>
            )}

            {/* Membership Section - shown after creation or in edit mode */}
            {showSubSections && effectiveMemberId && <MembershipSection memberId={effectiveMemberId} />}

            {/* Face Enrollment Section - shown after creation or in edit mode */}
            {showSubSections && effectiveMemberId && <FaceEnrollmentSection memberId={effectiveMemberId} />}
        </Box>
    );
};

// Sub-component for Membership Section — inline, no dialog
const MembershipSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const queryClient = useQueryClient();

    const [selectedPlanId, setSelectedPlanId] = React.useState('');
    const [startDate, setStartDate] = React.useState(format(new Date(), 'yyyy-MM-dd'));
    const [paymentMethod, setPaymentMethod] = React.useState<'cash' | 'transfer'>('cash');
    const [paymentAmount, setPaymentAmount] = React.useState<string>('');

    const { data: plansData } = useQuery({
        queryKey: ['membershipPlans', 'active'],
        queryFn: () => membershipPlansApi.getPlans(true)
    });
    const plans = plansData?.plans || [];

    const selectedPlan = plans.find((p: MembershipPlan) => p.id === selectedPlanId);

    // Auto-calculate end date from plan duration
    const endDate = React.useMemo(() => {
        if (!selectedPlan || !startDate) return '';
        const start = new Date(startDate);
        const end = addDays(start, selectedPlan.duration_days || 0);
        return format(end, 'yyyy-MM-dd');
    }, [selectedPlanId, startDate, selectedPlan]);

    // Auto-fill payment amount when plan changes
    React.useEffect(() => {
        if (selectedPlan) {
            setPaymentAmount(String(selectedPlan.price));
        }
    }, [selectedPlanId, selectedPlan]);

    const price = selectedPlan ? Number(selectedPlan.price) : 0;
    const paidAmount = Number(paymentAmount) || 0;
    const isPartial = paidAmount < price && paidAmount > 0;
    const isPending = paidAmount === 0;
    const isPaid = paidAmount >= price;

    const createMutation = useMutation({
        mutationFn: async (data: any) => {
            // 1. Create membership
            const membership = await membershipsApi.createMembership(data.membership);
            // 2. Create payment transaction if amount > 0
            if (data.payment.amount > 0) {
                await salesApi.createTransaction({
                    member_id: data.membership.member_id,
                    membership_id: membership.id,
                    amount: data.payment.amount,
                    payment_method: data.payment.method,
                    notes: data.payment.notes || undefined,
                });
            }
            return membership;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships'] });
            setSelectedPlanId('');
            setPaymentAmount('');
            setPaymentMethod('cash');
            setStartDate(format(new Date(), 'yyyy-MM-dd'));
        },
        onError: (error: any) => {
            alert(`Error: ${error.response?.data?.detail || error.message}`);
        }
    });

    const handleAssign = () => {
        if (!selectedPlan) return;
        createMutation.mutate({
            membership: {
                member_id: memberId,
                plan_id: selectedPlanId,
                type: selectedPlan.name,
                start_date: startDate,
                end_date: endDate,
                price: price,
            },
            payment: {
                amount: paidAmount,
                method: paymentMethod,
                notes: isPartial ? `Pago parcial. Pendiente: $${price - paidAmount}` : 'Pago completo',
            }
        });
    };

    const formatPlanLabel = (plan: MembershipPlan) => {
        const durationParts: string[] = [];
        if (plan.duration_months) durationParts.push(`${plan.duration_months}m`);
        if (plan.duration_days) durationParts.push(`${plan.duration_days}d`);
        const durationStr = durationParts.join(' ') || '0d';
        return `${plan.name} — $${Number(plan.price).toLocaleString()} (${durationStr})`;
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Typography variant="h6" gutterBottom>Assign Membership</Typography>

                <Box display="flex" flexDirection="column" gap={2} mt={1}>
                    {/* Plan Selection */}
                    <TextField
                        select
                        label="Select Plan"
                        value={selectedPlanId}
                        onChange={(e) => setSelectedPlanId(e.target.value)}
                        fullWidth
                        required
                    >
                        <MenuItem value=""><em>Choose a plan...</em></MenuItem>
                        {plans.map((plan: MembershipPlan) => (
                            <MenuItem key={plan.id} value={plan.id}>
                                {formatPlanLabel(plan)}
                            </MenuItem>
                        ))}
                    </TextField>

                    {/* Dates Row */}
                    <Grid container spacing={2}>
                        <Grid item xs={6}>
                            <TextField
                                label="Start Date"
                                type="date"
                                value={startDate}
                                onChange={(e) => setStartDate(e.target.value)}
                                fullWidth
                                InputLabelProps={{ shrink: true }}
                            />
                        </Grid>
                        <Grid item xs={6}>
                            <TextField
                                label="End Date"
                                type="date"
                                value={endDate}
                                fullWidth
                                InputLabelProps={{ shrink: true }}
                                InputProps={{ readOnly: true }}
                                helperText="Auto-calculated from plan"
                                sx={{ '& .MuiInputBase-input': { color: 'text.secondary' } }}
                            />
                        </Grid>
                    </Grid>

                    {/* Price Display (read-only) */}
                    {selectedPlan && (
                        <TextField
                            label="Plan Price"
                            value={`$${price.toLocaleString()}`}
                            fullWidth
                            InputProps={{ readOnly: true }}
                            sx={{ '& .MuiInputBase-input': { fontWeight: 'bold', fontSize: '1.1rem' } }}
                        />
                    )}

                    {/* Payment Section — only shown when a plan is selected */}
                    {selectedPlan && (
                        <>
                            <TextField
                                select
                                label="Payment Method"
                                value={paymentMethod}
                                onChange={(e) => setPaymentMethod(e.target.value as 'cash' | 'transfer')}
                                fullWidth
                            >
                                <MenuItem value="cash">💵 Efectivo (Cash)</MenuItem>
                                <MenuItem value="transfer">🏦 Transferencia (Transfer)</MenuItem>
                            </TextField>

                            {/* Payment Amount */}
                            <TextField
                                label="Payment Amount"
                                type="number"
                                value={paymentAmount}
                                onChange={(e) => setPaymentAmount(e.target.value)}
                                fullWidth
                                InputProps={{
                                    startAdornment: <InputAdornment position="start">$</InputAdornment>,
                                }}
                                helperText={
                                    isPaid ? "✅ Pago completo" :
                                    isPartial ? `⚠️ Pago parcial — Falta: $${(price - paidAmount).toLocaleString()}` :
                                    "❌ Sin pago (pendiente)"
                                }
                            />

                            {/* Payment Status Badge */}
                            <Box>
                                {isPaid && <Chip label="Pagado" color="success" />}
                                {isPartial && <Chip label={`Parcial: $${paidAmount.toLocaleString()} de $${price.toLocaleString()}`} color="warning" />}
                                {isPending && <Chip label="Pendiente" color="error" />}
                            </Box>
                        </>
                    )}

                    {/* Assign Button */}
                    <Button
                        onClick={handleAssign}
                        variant="contained"
                        size="large"
                        disabled={!selectedPlanId || createMutation.isPending}
                        fullWidth
                    >
                        {createMutation.isPending ? "Assigning..." : "Assign Membership"}
                    </Button>
                </Box>
            </CardContent>
        </Card>
    );
};

// Sub-component for Face Enrollment
const FaceEnrollmentSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const [enrollmentStatus, setEnrollmentStatus] = React.useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
    const [qualityScore, setQualityScore] = React.useState<number | null>(null);
    const fileInputRef = React.useRef<HTMLInputElement>(null);

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setEnrollmentStatus('uploading');
        try {
            const result = await membersApi.enrollBiometric(memberId, file);
            setQualityScore(result.quality_score);
            setEnrollmentStatus('success');
        } catch (error: any) {
            console.error('Enrollment failed:', error);
            setEnrollmentStatus('error');
        }
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Typography variant="h6" gutterBottom>Face Enrollment</Typography>

                {enrollmentStatus === 'success' ? (
                    <Box>
                        <Alert severity="success" sx={{ mb: 2 }}>
                            Face enrolled successfully! Quality score: {qualityScore?.toFixed(2)}
                        </Alert>
                    </Box>
                ) : (
                    <Box>
                        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                            Upload a clear photo of the member's face for biometric enrollment.
                        </Typography>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={handleFileUpload}
                            ref={fileInputRef}
                            style={{ display: 'none' }}
                        />
                        <Button
                            variant="outlined"
                            startIcon={<PhotoCamera />}
                            onClick={() => fileInputRef.current?.click()}
                            disabled={enrollmentStatus === 'uploading'}
                        >
                            {enrollmentStatus === 'uploading' ? 'Processing...' : 'Upload Face Photo'}
                        </Button>
                        {enrollmentStatus === 'error' && (
                            <Alert severity="error" sx={{ mt: 2 }}>
                                Enrollment failed. Make sure the photo has a clear, single face.
                            </Alert>
                        )}
                    </Box>
                )}
            </CardContent>
        </Card>
    );
};
